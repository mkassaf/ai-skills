#!/usr/bin/env python3
"""Render a timed storyboard as silent 1280x720/30fps editorial slide video."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1280, 720, 30
INK, MUTED = (37, 36, 58, 255), (98, 100, 119, 255)
VIOLET, COBALT = (107, 71, 200, 255), (36, 104, 165, 255)
ORANGE, CRANBERRY = (169, 83, 19, 255), (184, 63, 85, 255)
EDGE, CARD = (199, 190, 205, 190), (255, 255, 255, 248)
COLORS = {"violet": VIOLET, "purple": VIOLET, "cobalt": COBALT,
          "blue": COBALT, "orange": ORANGE, "cranberry": CRANBERRY,
          "red": CRANBERRY, "green": (57, 119, 84, 255)}
TINTS = {"violet": (243, 236, 251), "cobalt": (229, 242, 251),
         "orange": (251, 239, 229), "cranberry": (250, 235, 240),
         "green": (237, 247, 237)}
FONTS = ["/System/Library/Fonts/Avenir Next.ttc",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


@lru_cache(None)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in FONTS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size,
                                          index=(0 if bold else 7) if path.endswith(".ttc") else 0)
            except OSError:
                pass
    return ImageFont.load_default(size=size)


def color(value: str | None):
    if not value:
        return VIOLET
    key = str(value).lower().strip()
    if key in COLORS:
        return COLORS[key]
    if key.startswith("#") and len(key) == 7:
        try:
            return tuple(int(key[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
        except ValueError:
            pass
    raise ValueError(f"Unknown accent {value!r}; use a palette name or #RRGGBB")


def ease(value: float) -> float:
    value = max(0, min(1, value))
    return 1 - (1 - value) ** 3


def wrap(draw, value: str, ft, max_width: int):
    lines = []
    for paragraph in value.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}" if line else word
            if line and draw.textlength(candidate, font=ft) > max_width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


def draw_fit(draw, xy, value: str, box, preferred: int, minimum: int,
             fill, bold: bool = False):
    for size in range(preferred, minimum - 1, -1):
        ft = font(size, bold)
        lines = wrap(draw, value, ft, box[0])
        leading = round(size * 1.22)
        if len(lines) * leading <= box[1] and all(
                draw.textlength(line, font=ft) <= box[0] for line in lines):
            for i, line in enumerate(lines):
                draw.text((xy[0], xy[1] + i * leading), line, font=ft, fill=fill)
            return xy[1] + len(lines) * leading
    raise ValueError(f"Text too long for its slide area: {value[:90]!r}")


def rounded(draw, box, fill, outline=EDGE, radius=20, stroke=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=stroke)


def pill(draw, x, y, text, accent=VIOLET, w=52):
    rounded(draw, (x, y, x + w, y + 34), (249, 245, 252, 250), accent, 16, 1)
    draw.text((x + 15, y + 7), text, font=font(16, True), fill=accent)


def icon(draw, name, x, y, accent):
    if name == "target":
        for radius in (18, 10):
            draw.ellipse((x + 22 - radius, y + 22 - radius,
                          x + 22 + radius, y + 22 + radius), outline=accent, width=3)
        draw.ellipse((x + 18, y + 18, x + 26, y + 26), fill=accent)
    elif name == "check":
        draw.ellipse((x + 5, y + 5, x + 41, y + 41), outline=accent, width=3)
        draw.line((x + 14, y + 23, x + 20, y + 29, x + 33, y + 15),
                  fill=accent, width=4)
    elif name == "route":
        draw.ellipse((x + 5, y + 7, x + 12, y + 14), fill=accent)
        draw.ellipse((x + 32, y + 31, x + 39, y + 38), fill=accent)
        draw.arc((x + 8, y + 8, x + 36, y + 38), 10, 180, fill=accent, width=3)
    elif name == "shield":
        draw.polygon((x + 22, y + 5, x + 38, y + 11, x + 36, y + 28,
                      x + 22, y + 40, x + 8, y + 28, x + 6, y + 11), outline=accent)
        draw.line((x + 14, y + 22, x + 20, y + 28, x + 31, y + 16),
                  fill=accent, width=3)
    elif name == "list":
        for n in range(3):
            yy = y + 10 + n * 12
            draw.ellipse((x + 4, yy, x + 10, yy + 6), fill=accent)
            draw.line((x + 17, yy + 3, x + 41, yy + 3), fill=accent, width=3)
    else:
        for a, b in (((22, 4), (22, 40)), ((4, 22), (40, 22)),
                     ((9, 9), (35, 35)), ((35, 9), (9, 35))):
            draw.line((x + a[0], y + a[1], x + b[0], y + b[1]),
                      fill=accent, width=3)


def background():
    im = Image.new("RGB", (W, H))
    pixels = im.load()
    for y in range(H):
        fy = y / H
        for x in range(W):
            fx = x / W
            glow = max(0, 1 - math.hypot((fx - .18) * 1.35, (fy - .90) * 1.05))
            pixels[x, y] = (int(250 - 5 * fx - 5 * fy + 2 * glow),
                            int(248 - 5 * fx - 6 * fy + 2 * glow),
                            int(244 - 3 * fx - 5 * fy + 4 * glow))
    draw = ImageDraw.Draw(im)
    for x in range(0, W, 64):
        draw.line((x, 0, x, H), fill=(232, 226, 232))
    for y in range(0, H, 64):
        draw.line((0, y, W, y), fill=(232, 226, 232))
    draw.ellipse((-460, 250, 740, 1450), outline=(224, 216, 225))
    draw.ellipse((-300, 410, 580, 1290), outline=(227, 218, 227))
    return im.convert("RGBA")


BACKGROUND = background()


def card_boxes(layout, count):
    if layout == "pip":
        variants = {
            0: [], 1: [(72, 390, 734, 192)],
            2: [(72, 347, 734, 137), (72, 499, 734, 137)],
            3: [(72, 318 + i * 111, 734, 103) for i in range(3)],
            4: [(72 + i % 2 * 370, 330 + i // 2 * 150, 352, 138)
                for i in range(4)],
        }
    else:
        variants = {
            0: [], 1: [(73, 317, 1129, 262)],
            2: [(72 + i * 571, 314, 548, 265) for i in range(2)],
            3: [(72 + i * 380, 310, 358, 269) for i in range(3)],
            4: [(72 + i * 287, 310, 266, 269) for i in range(4)],
            5: [(72 + i % 3 * 380, 310 + i // 3 * 149, 358, 137)
                for i in range(5)],
            6: [(72 + i % 3 * 380, 310 + i // 3 * 149, 358, 137)
                for i in range(6)],
        }
    if count not in variants:
        raise ValueError(f"Too many cards for {layout} scene: {count}")
    return variants[count]


class Layer:
    def __init__(self, image, x, y, start, end, travel=18):
        self.image, self.x, self.y = image, x, y
        self.start, self.end, self.travel = start, end, travel

    def paint(self, dst, t):
        if not self.start <= t < self.end:
            return
        opening = ease((t - self.start) / .44)
        opacity = opening * ease((self.end - t) / .25)
        if opacity <= 0:
            return
        y = self.y + round((1 - opening) * self.travel)
        if opacity > .995:
            dst.alpha_composite(self.image, (self.x, y))
        else:
            faded = self.image.copy()
            faded.putalpha(faded.getchannel("A").point(
                lambda value: round(value * opacity)))
            dst.alpha_composite(faded, (self.x, y))


def layer(x, y, w, h, start, end, painter, travel=18):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    painter(ImageDraw.Draw(im))
    return Layer(im, x, y, start, end, travel)


def card_layer(box, item, number, start, end):
    x, y, w, h = box
    accent = color(item.get("accent"))
    shape = item.get("icon", ["target", "spark", "check", "route", "list", "shield"][(number - 1) % 6])

    def paint(draw):
        rounded(draw, (2, 2, w - 3, h - 3), CARD, (*accent[:3], 145), 22)
        draw.rounded_rectangle((3, 3, 10, h - 4), radius=3, fill=accent)
        compact = h <= 200
        if 155 < h <= 200:
            pill(draw, 24, 24, f"{number:02d}", accent)
            icon(draw, shape, w - 76, 24, accent)
            tx, ty, th, ts, by, bs = 94, 22, 55, 30, 82, 22
        elif compact:
            pill(draw, 21, 18, f"{number:02d}", accent)
            tx, ty = 89, 13
            th, ts = (43 if h < 120 else 56), (25 if w >= 450 else 22)
            by, bs = (52 if h < 120 else 65), (17 if w >= 450 else 15)
        else:
            pill(draw, 24, 22, f"{number:02d}", accent)
            icon(draw, shape, w - 75, 23, accent)
            draw.line((24, 168, w - 26, 168), fill=accent, width=3)
            tx, ty, th, ts, by, bs = 24, 91, 76, (34 if w >= 420 else 30), 180, 20
        title_end = draw_fit(draw, (tx, ty), str(item["title"]),
                             (w - tx - 20, th), ts, 15, INK, True)
        body = str(item.get("body", ""))
        if body:
            by = max(by, title_end + 3)
            draw_fit(draw, (tx, by), body, (w - tx - 22, max(20, h - by - 12)),
                     bs, 12, MUTED)

    return layer(x, y, w, h, start, end, paint)


class StoryRenderer:
    def __init__(self, story):
        self.story = story
        self.duration = float(story["duration"])
        self.scenes = story["scenes"]
        if self.duration <= 0 or not self.scenes:
            raise ValueError("Storyboard needs positive duration and scenes")
        expected = 0.0
        for i, scene in enumerate(self.scenes, 1):
            start, end = float(scene["start"]), float(scene["end"])
            if abs(start - expected) > .01 or end <= start:
                raise ValueError(f"Scene {i} must start at {expected:g} and end later")
            if scene.get("layout") not in ("pip", "full"):
                raise ValueError(f"Scene {i}: layout must be pip or full")
            for key in ("section", "headline"):
                if not str(scene.get(key, "")).strip():
                    raise ValueError(f"Scene {i} needs {key}")
            for card in scene.get("cards", []):
                if not str(card.get("title", "")).strip():
                    raise ValueError(f"Scene {i} has a card without title")
                if "start" in card and not start <= float(card["start"]) < end:
                    raise ValueError(f"Scene {i} has card start outside its scene")
                color(card.get("accent"))
            card_boxes(scene["layout"], len(scene.get("cards", [])))
            expected = end
        if abs(expected - self.duration) > .01:
            raise ValueError("Last scene end must equal storyboard duration")
        self.bases = [self.make_base(scene, i) for i, scene in enumerate(self.scenes)]
        self.boxes = [card_boxes(scene["layout"], len(scene.get("cards", [])))
                      for scene in self.scenes]
        self.layers = [self.make_layers(scene, boxes)
                       for scene, boxes in zip(self.scenes, self.boxes)]

    def make_base(self, scene, index):
        colorway = str(scene.get("colorway", list(TINTS)[index % len(TINTS)])).lower()
        if colorway not in TINTS:
            raise ValueError(f"Unknown colorway {colorway!r}")
        dst = Image.blend(BACKGROUND,
                          Image.new("RGBA", (W, H), (*TINTS[colorway], 255)), .30)
        draw = ImageDraw.Draw(dst)
        draw_fit(draw, (68, 34), str(self.story.get("title") or self.scenes[0]["section"]).upper(),
                 (420, 35), 24, 15, INK, True)
        draw.text((547, 39), "/  EXPLAINED", font=font(16, True), fill=VIOLET)
        pill(draw, 1046, 35, f"{index + 1:02d}  /  {len(self.scenes):02d}", VIOLET, 166)
        draw.line((68, 82, 1212, 82), fill=(190, 180, 201, 210), width=2)
        draw.text((69, 674), str(scene["section"]).upper(),
                  font=font(13, True), fill=MUTED)
        mm, ss = divmod(round(self.duration), 60)
        clock_x = 780 if scene["layout"] == "pip" else 1151
        draw.text((clock_x, 674), f"{mm:02d}:{ss:02d}", font=font(13, True), fill=MUTED)
        if scene["layout"] == "pip":
            rounded(draw, (859, 407, 1236, 683), (255, 255, 255, 246),
                    (171, 150, 207, 165), 25)
            draw.line((878, 394, 950, 394), fill=VIOLET, width=3)
            draw.text((962, 383), "PRESENTER", font=font(14, True), fill=VIOLET)
        return dst

    def make_layers(self, scene, boxes):
        start, end = float(scene["start"]), float(scene["end"])
        layers = []
        headline = str(scene["headline"])

        def head(draw):
            draw_fit(draw, (1, 1), headline, (1127, 134), 55, 31,
                     color(scene["headline_accent"]) if scene.get("headline_accent") else INK,
                     True)

        layers.append(layer(70, 119, 1140, 137, start + .10, end, head))
        if scene.get("subhead"):
            def sub(draw):
                draw_fit(draw, (1, 1), str(scene["subhead"]),
                         ((734 if scene["layout"] == "pip" else 1125), 70),
                         25, 17, MUTED)
            sub_width = 742 if scene["layout"] == "pip" else 1133
            layers.append(layer(73, 247, sub_width, 72, start + .44, end, sub))
        for i, (item, box) in enumerate(zip(scene.get("cards", []), boxes), 1):
            show = float(item.get("start", start + .70 + (i - 1) * .40))
            card_end = float(item.get("end", end))
            if not start <= show < card_end <= end:
                raise ValueError(f"Card {i} has timing outside scene")
            layers.append(card_layer(box, item, i, show, card_end))
        callout = scene.get("callout")
        if callout:
            if isinstance(callout, str):
                callout = {"text": callout}
            phrase = str(callout.get("text", ""))
            if phrase:
                show = float(callout.get("start", start + min(2.4, (end - start) * .65)))
                if not start <= show < end:
                    raise ValueError("Callout start is outside scene")
                xy, size = ((863, 306), (344, 70)) if scene["layout"] == "pip" else ((72, 603), (1135, 49))
                accent = color(callout.get("accent"))

                def paint_callout(draw):
                    draw.line((4, 4, 4, size[1] - 5), fill=accent, width=4)
                    draw_fit(draw, (16, 2), phrase, (size[0] - 22, size[1] - 4),
                             21, 15, accent, True)

                layers.append(layer(*xy, *size, show, end, paint_callout, 11))
        return layers

    def scene_frame(self, index, t):
        scene = self.scenes[index]
        dst = self.bases[index].copy()
        draw = ImageDraw.Draw(dst)
        boxes = self.boxes[index]
        if len(boxes) >= 2:
            progress = max(0, min(1, (t - float(scene["start"])) /
                                   (float(scene["end"]) - float(scene["start"]))))
            if scene["layout"] == "pip" and len(boxes) <= 3:
                first, last = boxes[0][1] + 38, boxes[-1][1] + 38
                cursor = first + round((last - first) * progress)
                draw.line((59, first, 59, last), fill=EDGE, width=3)
                draw.line((59, first, 59, cursor), fill=VIOLET, width=4)
                draw.ellipse((54, cursor - 5, 64, cursor + 5), fill=VIOLET)
            else:
                xs = [box[0] + box[2] // 2 for box in boxes[:4]]
                cursor = xs[0] + round((xs[-1] - xs[0]) * progress)
                draw.line((xs[0], 296, xs[-1], 296), fill=EDGE, width=4)
                draw.line((xs[0], 296, cursor, 296), fill=VIOLET, width=4)
                draw.ellipse((cursor - 5, 291, cursor + 5, 301), fill=VIOLET)
        for item in self.layers[index]:
            item.paint(dst, t)
        draw = ImageDraw.Draw(dst)
        cursor = 68 + round(1144 * max(0, min(1, t / self.duration)))
        draw.line((68, 81, cursor, 81), fill=VIOLET, width=3)
        draw.ellipse((cursor - 4, 77, cursor + 4, 85), fill=VIOLET)
        return dst

    def frame_at(self, t):
        index = next((i for i, scene in enumerate(self.scenes)
                      if float(scene["start"]) <= t < float(scene["end"])),
                     len(self.scenes) - 1)
        image = self.scene_frame(index, t)
        if index > 0:
            scene_start = float(self.scenes[index]["start"])
            if t < scene_start + .22:
                previous = self.scene_frame(index - 1, scene_start - 1 / FPS)
                image = Image.blend(previous, image, ease((t - scene_start) / .22))
        return image.convert("RGB")


def ffmpeg_path(given):
    if given:
        return given
    return os.environ.get("FFMPEG") or shutil.which("ffmpeg") or next((path for path in
        ["/Applications/Weline Pro.app/Contents/Resources/mac_pc_nas/ffmpeg"]
        if Path(path).exists()), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--preview-dir", type=Path)
    parser.add_argument("--ffmpeg")
    args = parser.parse_args()
    story = json.loads(args.storyboard.read_text(encoding="utf-8"))
    renderer = StoryRenderer(story)
    if args.preview_dir:
        args.preview_dir.mkdir(parents=True, exist_ok=True)
        for i, scene in enumerate(renderer.scenes, 1):
            start, end = float(scene["start"]), float(scene["end"])
            moment = max(start, end - min(.45, (end - start) * .15))
            renderer.frame_at(moment).save(
                args.preview_dir / f"scene-{i:02d}.png")
    ffmpeg = ffmpeg_path(args.ffmpeg)
    if not ffmpeg:
        raise SystemExit("FFmpeg not found; pass --ffmpeg /path/to/ffmpeg")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo",
               "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
               "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(args.out)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    frames = math.ceil(renderer.duration * FPS)
    try:
        for n in range(frames):
            process.stdin.write(renderer.frame_at(n / FPS).tobytes())
            if n % 300 == 0:
                print(f"Rendered {n}/{frames} frames", flush=True)
        process.stdin.close()
        stderr = process.stderr.read().decode("utf-8", "replace")
        code = process.wait()
    except Exception:
        process.kill()
        process.wait()
        raise
    if code:
        raise RuntimeError(f"FFmpeg failed ({code}): {stderr[-2000:]}")
    print(args.out)


if __name__ == "__main__":
    main()
