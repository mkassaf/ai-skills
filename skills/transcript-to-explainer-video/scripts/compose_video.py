#!/usr/bin/env python3
"""Compose storyboard slides, a presenter window, and narration into an MP4.

The storyboard uses 1280x720/30 fps and `scenes[].layout` = `pip` or `full`.
`full` scenes hide the presenter with a short fade. An office backdrop requires a
person matte made with render_office_mask.swift. All inputs start at time zero.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw


FPS = 30
PIP_W, PIP_H = 360, 260
DEFAULT_X, DEFAULT_Y = 868, 416
DEFAULT_FADE = 0.38
BUNDLED_BORDER = Path(__file__).resolve().parent.parent / "assets" / "pip-frame.png"
KNOWN_FFMPEG = Path("/Applications/Weline Pro.app/Contents/Resources/mac_pc_nas/ffmpeg")


def ffmpeg_binary(explicit: str | None) -> str:
    candidate = explicit or os.environ.get("FFMPEG") or shutil.which("ffmpeg")
    if candidate:
        return candidate
    if KNOWN_FFMPEG.exists():
        return str(KNOWN_FFMPEG)
    raise RuntimeError("FFmpeg is required. Put it on PATH or set FFMPEG=/path/to/ffmpeg.")


def storyboard_settings(path: Path) -> tuple[float, list[tuple[float, float]], bool]:
    board = json.loads(path.read_text())
    scenes = board.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Storyboard needs a nonempty scenes array")
    duration = float(board.get("duration", max(float(s["end"]) for s in scenes)))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Storyboard duration must be positive")
    if int(board.get("fps", FPS)) != FPS:
        raise ValueError("This compositor requires a 30 fps storyboard")

    hidden: list[tuple[float, float]] = []
    has_pip = False
    for scene in scenes:
        start, end = float(scene["start"]), float(scene["end"])
        layout = scene["layout"]
        if not (0 <= start < end <= duration + 0.01):
            raise ValueError(f"Invalid scene interval: {scene}")
        if layout == "full":
            hidden.append((start, end))
        elif layout == "pip":
            has_pip = True
        else:
            raise ValueError(f"Unknown scene layout {layout!r}; use 'full' or 'pip'")

    # Adjacent full-screen scenes are one continuous presenter-free section.
    merged: list[tuple[float, float]] = []
    for start, end in sorted(hidden):
        if merged and start <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return duration, merged, has_pip


def opacity(t: float, hidden: list[tuple[float, float]], fade: float) -> float:
    level = 1.0
    for start, end in hidden:
        if start - fade <= t < start:
            level = min(level, (start - t) / fade)
        elif start <= t <= end:
            level = 0.0
        elif end < t < end + fade:
            level = min(level, (t - end) / fade)
    return max(0.0, min(1.0, level))


def make_outer_mask(
    ffmpeg: str, path: Path, duration: float,
    hidden: list[tuple[float, float]], fade: float,
) -> None:
    # Antialias corners by drawing at 4x and reducing with Lanczos.
    hi = Image.new("L", (PIP_W * 4, PIP_H * 4), 0)
    ImageDraw.Draw(hi).rounded_rectangle(
        (0, 0, PIP_W * 4 - 1, PIP_H * 4 - 1), radius=48, fill=255
    )
    shape = hi.resize((PIP_W, PIP_H), Image.Resampling.LANCZOS)
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "gray", "-video_size", f"{PIP_W}x{PIP_H}",
        "-framerate", str(FPS), "-i", "pipe:0", "-an",
        "-c:v", "ffv1", "-pix_fmt", "gray", str(path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    cache: dict[int, bytes] = {}
    try:
        for frame in range(math.ceil(duration * FPS)):
            level = round(opacity(frame / FPS, hidden, fade) * 255)
            if level not in cache:
                cache[level] = shape.point(lambda pixel: (pixel * level + 127) // 255).tobytes()
            proc.stdin.write(cache[level])
    finally:
        proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("FFmpeg failed to encode the presenter visibility mask")


def compose(args: argparse.Namespace) -> None:
    ffmpeg = ffmpeg_binary(args.ffmpeg)
    board = Path(args.storyboard).expanduser().resolve()
    base = Path(args.slides).expanduser().resolve()
    dest = Path(args.out).expanduser().resolve()
    for item in (board, base):
        if not item.is_file():
            raise FileNotFoundError(item)
    duration, hidden, has_pip = storyboard_settings(board)

    source = Path(args.source).expanduser().resolve() if args.source else None
    audio = Path(args.audio).expanduser().resolve() if args.audio else None
    office = Path(args.office_bg).expanduser().resolve() if args.office_bg else None
    matte = Path(args.person_mask).expanduser().resolve() if args.person_mask else None
    border = Path(args.border).expanduser().resolve() if args.border else BUNDLED_BORDER
    for item in (source, audio, office, matte):
        if item is not None and not item.is_file():
            raise FileNotFoundError(item)
    if args.border and not border.is_file():
        raise FileNotFoundError(border)
    if office and not source:
        raise ValueError("--office-bg needs --source")
    if office and not matte:
        raise ValueError("--office-bg needs --person-mask from render_office_mask.swift")
    if matte and not office:
        raise ValueError("--person-mask is only used with --office-bg")
    if not (0 <= args.pip_x <= 1280 - PIP_W and 0 <= args.pip_y <= 720 - PIP_H):
        raise ValueError("Presenter window must fit inside the 1280x720 slide")
    if args.fade <= 0:
        raise ValueError("--fade must be positive")

    dest.parent.mkdir(parents=True, exist_ok=True)
    show_pip = source is not None and has_pip
    with tempfile.TemporaryDirectory(prefix="explainer_compose_") as temp_dir:
        inputs = ["-i", str(base)]
        next_index = 1

        def add_video(path: Path, loop: bool = False) -> int:
            nonlocal next_index
            index = next_index
            next_index += 1
            if loop:
                inputs.extend(["-loop", "1", "-framerate", str(FPS)])
            inputs.extend(["-i", str(path)])
            return index

        source_i = add_video(source) if source else None
        matte_i = add_video(matte) if show_pip and matte else None
        office_i = add_video(office, loop=True) if show_pip and office else None
        border_i = add_video(border, loop=True) if show_pip and border.is_file() else None
        outer_i = None
        if show_pip:
            outer_path = Path(temp_dir) / "presenter_visibility.mkv"
            make_outer_mask(ffmpeg, outer_path, duration, hidden, args.fade)
            outer_i = add_video(outer_path)
        audio_i = add_video(audio) if audio else None

        graph: list[str] = []
        if show_pip:
            assert source_i is not None and outer_i is not None
            graph.append(
                f"[{source_i}:v]fps={FPS},scale={PIP_W}:{PIP_H}:"
                "force_original_aspect_ratio=increase,"
                f"crop={PIP_W}:{PIP_H},"
                "eq=contrast=1.07:brightness=-0.02:saturation=0.91,"
                "format=rgba,setpts=PTS-STARTPTS[person]"
            )
            current = "person"
            if office_i is not None:
                assert matte_i is not None
                graph.append(
                    f"[{matte_i}:v]fps={FPS},scale={PIP_W}:{PIP_H},"
                    "format=gray,setpts=PTS-STARTPTS[seg]"
                )
                graph.append("[person][seg]alphamerge[person_a]")
                graph.append(
                    f"[{office_i}:v]scale={PIP_W}:{PIP_H},format=rgba[office]"
                )
                graph.append(
                    "[office][person_a]overlay=0:0:shortest=1:format=auto,"
                    "format=rgba[pip_office]"
                )
                current = "pip_office"
            if border_i is not None:
                graph.append(f"[{border_i}:v]scale={PIP_W}:{PIP_H},format=rgba[border]")
                graph.append(
                    f"[{current}][border]overlay=0:0:shortest=1:format=auto,"
                    "format=rgba[pip_framed]"
                )
                current = "pip_framed"
            graph.append(f"[{outer_i}:v]format=gray,setpts=PTS-STARTPTS[outer]")
            graph.append(f"[{current}][outer]alphamerge[pip_alpha]")
            graph.append(
                f"[0:v][pip_alpha]overlay={args.pip_x}:{args.pip_y}:"
                "shortest=0:eof_action=pass:format=auto,format=yuv420p[v]"
            )

        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", *inputs]
        if graph:
            cmd.extend(["-filter_complex", ";".join(graph), "-map", "[v]"])
        else:
            cmd.extend(["-map", "0:v:0"])
        if audio_i is not None:
            cmd.extend(["-map", f"{audio_i}:a:0", "-af", "apad"])
        elif source_i is not None:
            cmd.extend(["-map", f"{source_i}:a:0?", "-af", "apad"])
        else:
            cmd.append("-an")
        cmd.extend([
            "-t", f"{duration:.6f}", "-r", str(FPS),
            "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(dest),
        ])
        subprocess.run(cmd, check=True)
    print(f"Wrote {dest} ({duration:.2f}s, {FPS} fps)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", required=True, help="JSON scene timing and layouts")
    parser.add_argument("--slides", required=True, help="Rendered slide MP4")
    parser.add_argument("--out", required=True, help="Output H.264/AAC MP4")
    parser.add_argument("--source", help="Talking-head video, aligned to storyboard at time zero")
    parser.add_argument("--audio", help="Independent narration audio; overrides source audio")
    parser.add_argument("--office-bg", help="Office image displayed behind the presenter")
    parser.add_argument("--person-mask", help="360x260/30fps grayscale person matte video")
    parser.add_argument("--border", help="Transparent 360x260 border PNG")
    parser.add_argument("--pip-x", type=int, default=DEFAULT_X)
    parser.add_argument("--pip-y", type=int, default=DEFAULT_Y)
    parser.add_argument("--fade", type=float, default=DEFAULT_FADE)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--preset", default="medium")
    parser.add_argument("--ffmpeg", help="FFmpeg binary; also accepts FFMPEG environment variable")
    args = parser.parse_args()
    try:
        compose(args)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"compose_video: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
