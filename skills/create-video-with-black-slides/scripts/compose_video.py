#!/usr/bin/env python3
"""Composite timed black slides, an optional matted presenter, and narration.

Storyboard times and the slides MP4 start at zero. ``--start`` selects a region
of the original presenter video and its whole-source matte together. Embedded
source audio follows that trim; a separate ``--audio`` is an override already
aligned to the selected timeline.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

from common import ffmpeg_binary


def positive_number(value: object, name: str, *, zero_ok: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(number) or number < 0 or (number == 0 and not zero_ok):
        qualifier = "nonnegative" if zero_ok else "positive"
        raise ValueError(f"{name} must be a finite {qualifier} number")
    return number


def integer_dimension(value: object, name: str) -> int:
    number = positive_number(value, name)
    if not number.is_integer() or int(number) % 2:
        raise ValueError(f"{name} must be a positive even integer for H.264 output")
    return int(number)


def read_storyboard(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        story = json.load(handle)
    if not isinstance(story, dict):
        raise ValueError("storyboard must be a JSON object")
    if "duration" not in story:
        raise ValueError("storyboard requires duration in seconds")
    duration = positive_number(story["duration"], "duration")
    fade_in = positive_number(story.get("fade_in", 0.35), "fade_in", zero_ok=True)
    fade_out = positive_number(story.get("fade_out", 0.45), "fade_out", zero_ok=True)
    # Share short clips proportionally so the fades never overlap.
    if fade_in + fade_out > duration:
        factor = duration / (fade_in + fade_out)
        fade_in *= factor
        fade_out *= factor
    return {
        "width": integer_dimension(story.get("width", 1280), "width"),
        "height": integer_dimension(story.get("height", 720), "height"),
        "fps": positive_number(story.get("fps", 30), "fps"),
        "duration": duration,
        "fade_in": fade_in,
        "fade_out": fade_out,
    }


def n(value: float) -> str:
    return f"{value:.9g}"


def fitted_video(story: dict, *, gray: bool = False) -> str:
    width, height = story["width"], story["height"]
    pixel_format = "gray" if gray else "rgba"
    return (
        f"fps={n(story['fps'])},"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,format={pixel_format}"
    )


def video_graph(story: dict, indices: dict[str, int]) -> str:
    """Keep presenter PTS so embedded audio/video retain their original offset."""
    filters = []
    slides = indices["slides"]
    # Generated slides are a standalone timeline, unlike the original source.
    filters.append(
        f"[{slides}:v:0]setpts=PTS-STARTPTS,{fitted_video(story)},format=gbrp[graphics]"
    )
    if "source" in indices:
        source, mask = indices["source"], indices["mask"]
        filters.extend([
            f"[{source}:v:0]{fitted_video(story)}[src]",
            f"[{mask}:v:0]{fitted_video(story, gray=True)}[mask]",
            "[src][mask]alphamerge=shortest=1[person]",
            f"color=c=black:s={story['width']}x{story['height']}:"
            f"r={n(story['fps'])}:d={n(story['duration'])},format=rgba[black]",
            "[black][person]overlay=0:0:eof_action=pass:repeatlast=0:"
            "shortest=0:format=rgb,format=gbrp[cutout]",
            "[cutout][graphics]blend=all_mode=screen:shortest=1[composite]",
        ])
        label = "composite"
    else:
        label = "graphics"
    finish = ["format=yuv420p"]
    if story["fade_in"]:
        finish.append(f"fade=t=in:st=0:d={n(story['fade_in'])}")
    if story["fade_out"]:
        finish.append(
            f"fade=t=out:st={n(story['duration'] - story['fade_out'])}:"
            f"d={n(story['fade_out'])}"
        )
    filters.append(f"[{label}]{','.join(finish)}[v]")
    return ";".join(filters)


def probe_media(ffmpeg: str, path: Path) -> dict:
    """Get stream coverage, preferring ffprobe but supporting FFmpeg-only installs."""
    sibling = Path(ffmpeg).with_name("ffprobe")
    ffprobe = str(sibling) if sibling.is_file() else shutil.which("ffprobe")
    if ffprobe:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode:
            raise ValueError(f"cannot probe {path}: {result.stderr.strip()}")
        info = json.loads(result.stdout)
        container_duration = info.get("format", {}).get("duration")
        streams = {}
        for stream in info.get("streams", []):
            kind = stream.get("codec_type")
            if kind not in {"audio", "video"} or kind in streams:
                continue
            # Matroska often stores track duration as a tag instead.
            duration = stream.get("duration") or stream.get("tags", {}).get("DURATION")
            if duration and ":" in str(duration):
                h, m, s = str(duration).split(":")
                duration = float(h) * 3600 + float(m) * 60 + float(s)
            if duration in {None, "N/A"}:
                duration = container_duration
            if duration in {None, "N/A"}:
                streams[kind] = None
            else:
                streams[kind] = float(duration)
        return streams
    # The ffmpeg inspection command intentionally has no output. Its stderr
    # supplies container duration and stream presence when ffprobe is absent.
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True, text=True, check=False,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    duration = None
    if match:
        duration = int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])
    streams = {}
    for kind in ("video", "audio"):
        if re.search(rf"Stream\s+#.*?:\s*{kind.title()}:", result.stderr):
            streams[kind] = duration
    if not streams:
        raise ValueError(f"cannot read media streams in {path}: {result.stderr.strip()}")
    return streams


def require_coverage(info: dict, kind: str, path: Path, required: float, tolerance: float) -> None:
    if kind not in info:
        raise ValueError(f"no readable {kind} stream in {path}")
    duration = info[kind]
    if duration is None or not math.isfinite(duration):
        raise ValueError(f"cannot determine {kind} duration in {path}; refusing an unverifiable export")
    if duration + tolerance < required:
        raise ValueError(
            f"{path} has only {duration:.3f}s of {kind}; {required:.3f}s is required "
            "to cover the storyboard and selected source start"
        )


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--storyboard", type=Path, required=True, help="JSON containing duration, optional width/height/fps/fade_in/fade_out")
    ap.add_argument("--slides", type=Path, required=True, help="Black-background graphics MP4, starting at timeline zero")
    ap.add_argument("--out", type=Path, required=True, help="Output MP4")
    ap.add_argument("--source", type=Path, help="Optional original presenter video with embedded audio")
    ap.add_argument("--person-mask", type=Path, help="Whole-source grayscale matte; required with --source")
    ap.add_argument("--audio", type=Path, help="Narration override aligned to timeline zero; not trimmed by --start")
    ap.add_argument("--start", type=float, default=0, help="Seconds to trim from both source and whole-source mask (default: 0)")
    ap.add_argument("--normalize-audio", action="store_true", help="Apply a 75 Hz high-pass and loudnorm I=-16, TP=-1.5, LRA=11")
    ap.add_argument("--denoise-floor", type=float, help="Optional afftdn noise floor in dB, from -80 to -20; omitted by default")
    ap.add_argument("--silent", action="store_true", help="Explicitly make a silent video, ignoring source audio")
    ap.add_argument("--crf", type=int, default=18, help="H.264 CRF (default: 18)")
    ap.add_argument("--preset", default="medium", help="H.264 encoding preset (default: medium)")
    ap.add_argument("--ffmpeg", help="Explicit FFmpeg executable")
    return ap


def main() -> None:
    ap = parser()
    args = ap.parse_args()
    try:
        args.start = positive_number(args.start, "--start", zero_ok=True)
        if not 0 <= args.crf <= 51:
            raise ValueError("--crf must be from 0 to 51")
        if args.denoise_floor is not None and (
            not math.isfinite(args.denoise_floor) or not -80 <= args.denoise_floor <= -20
        ):
            raise ValueError("--denoise-floor must be from -80 to -20 dB")
        if args.source and not args.person_mask:
            raise ValueError("--source requires --person-mask")
        if args.person_mask and not args.source:
            raise ValueError("--person-mask requires --source")
        if args.silent and args.audio:
            raise ValueError("--silent and --audio cannot be combined")
        if args.start and not args.source:
            raise ValueError("--start requires --source; slides and override audio already start at timeline zero")
        inputs = [args.storyboard, args.slides, args.source, args.person_mask, args.audio]
        for path in inputs:
            if path is not None and not path.is_file():
                raise ValueError(f"input file does not exist: {path}")
        output = args.out.expanduser().resolve()
        if any(
            path is not None and (
                path.resolve() == output or (output.exists() and path.samefile(output))
            ) for path in inputs
        ):
            raise ValueError("output must differ from every input file")
        story = read_storyboard(args.storyboard)
        ffmpeg = ffmpeg_binary(args.ffmpeg)
        media = {path: probe_media(ffmpeg, path) for path in inputs[1:] if path is not None}
        tolerance = 1 / story["fps"] + 0.005
        require_coverage(media[args.slides], "video", args.slides, story["duration"], tolerance)
        if args.source:
            require_coverage(media[args.source], "video", args.source, args.start + story["duration"], tolerance)
            require_coverage(media[args.person_mask], "video", args.person_mask, args.start + story["duration"], tolerance)
        audio_path = None if args.silent else args.audio or args.source
        if audio_path is None and not args.silent:
            raise ValueError("provide --audio or a source with audio, or explicitly use --silent")
        if audio_path is not None:
            if "audio" not in media[audio_path]:
                raise ValueError(f"no readable audio stream in {audio_path}; provide --audio or explicitly use --silent")
            needed = story["duration"] + (args.start if not args.audio else 0)
            require_coverage(media[audio_path], "audio", audio_path, needed, tolerance)
    except (OSError, ValueError, RuntimeError) as exc:
        ap.error(str(exc))

    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "warning", "-stats"]
    indices: dict[str, int] = {}
    if args.source:
        indices["source"] = 0
        # Let FFmpeg shift the whole input timebase after seeking. Do not apply
        # asetpts/video STARTPTS resets, which can erase original A/V offsets.
        cmd += ["-ss", n(args.start), "-i", str(args.source)]
        indices["mask"] = 1
        cmd += ["-ss", n(args.start), "-i", str(args.person_mask)]
    indices["slides"] = len(indices)
    cmd += ["-i", str(args.slides)]
    if args.audio:
        indices["audio"] = len(indices)
        cmd += ["-i", str(args.audio)]
    cmd += ["-filter_complex", video_graph(story, indices), "-map", "[v]"]
    if audio_path is not None:
        audio_index = indices["audio"] if args.audio else indices["source"]
        cmd += ["-map", f"{audio_index}:a:0"]
        audio_filters = []
        if args.normalize_audio:
            audio_filters.append("highpass=f=75")
        if args.denoise_floor is not None:
            audio_filters.append(f"afftdn=nf={n(args.denoise_floor)}:tn=1")
        if args.normalize_audio:
            audio_filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
        if audio_filters:
            cmd += ["-af", ",".join(audio_filters)]
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    else:
        cmd += ["-an"]
    cmd += [
        "-t", n(story["duration"]), "-r", n(story["fps"]),
        "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
        "-pix_fmt", "yuv420p", "-map_metadata", "-1", "-movflags", "+faststart", str(output),
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"FFmpeg composition failed (exit {exc.returncode})") from exc
    print(output)


if __name__ == "__main__":
    main()
