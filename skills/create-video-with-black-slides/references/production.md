# Production helpers and operational lessons

Python helpers need Pillow. Optional mask cleanup also needs NumPy; component cleanup needs SciPy. The macOS person helper needs Swift and Vision. Locate usable installed runtimes/libraries before installing replacements. FFmpeg discovery checks an explicit override, `FFMPEG`, PATH, and known local macOS locations.

## Speech and timeline

Extract narration and obtain phrase or word timestamps with an available transcription tool. Check accented technical terms against the recording. Preserve the source audio/video offset: audio extracted into a WAV can begin at the first audio packet while the source video begins earlier. Include that offset in storyboard timing when needed.

MLX Whisper is a useful local option when already installed. Some cached MLX models call their weights `model.safetensors`, while a package expects `weights.safetensors`. If needed, create a task-local model directory with correctly named symlinks and its config; leave the shared cache untouched. Disable previous-text conditioning when repeated hallucinations appear. Do not hardcode a prior task's environment or model path into a new job.

`compose_video.py --start N` trims the original source and its full-timeline matte together. Graphics and an optional `--audio` override are already relative to the final timeline and are not trimmed by this option. To use a nonzero start, generate the matte from time zero through at least `N + final duration`. The Swift helper can render a subsection for diagnostics; such a subsection is not a full-timeline matte. Avoid trimming it again by accident.

## Commands

In these examples, `SKILL_DIR` is the installed skill directory; use actual absolute paths for the task's files.

Render graphics or previews:

```bash
python3 "$SKILL_DIR/scripts/render_slides.py" --storyboard work/storyboard.json --out work/slides.mp4
python3 "$SKILL_DIR/scripts/render_slides.py" --storyboard work/storyboard.json --preview-dir work/previews --times 2,15,30
```

Set preview times within the new storyboard duration. The graphics encoder uses H.264 CRF16. The compositor defaults to CRF18. Both use the storyboard's canvas and frame rate.

Generate a full-frame matte on macOS (white = person, black = room):

```bash
swift "$SKILL_DIR/scripts/render_person_mask.swift" SOURCE.mov 0 DURATION work/person-mask.mkv
```

The optional trailing arguments `WIDTH HEIGHT FPS` override 1280×720/30fps. The helper uses accurate Vision segmentation on a smaller fitted frame and upscales the matte with gentle edge cleanup. It fits and pads instead of cropping. It applies no source-specific exclusion boxes. Check fingers and hair; change its edge treatment or use another suitable matte if it erodes foreground detail.

Compose the presenter on black with marker graphics in front:

```bash
python3 "$SKILL_DIR/scripts/compose_video.py" --storyboard work/storyboard.json --slides work/slides.mp4 --source SOURCE.mov --person-mask work/person-mask.mkv --normalize-audio --out outputs/final.mp4
```

This applies the matte, places the presenter against pure black, and uses screen blending for luminous foreground diagrams. Keep graphics clear of the face. Source audio is retained unless `--audio narration.wav` overrides it. `--normalize-audio` uses a 75Hz high-pass and targets about −16 LUFS / −1.5dB true peak; inspect the result. Noise reduction is opt-in via `--denoise-floor` and needs listening checks.

For narration without presenter footage:

```bash
python3 "$SKILL_DIR/scripts/compose_video.py" --storyboard work/storyboard.json --slides work/slides.mp4 --audio narration.wav --normalize-audio --out outputs/final.mp4
```

For an intentional hold after narration, pad the narration file with silence first (for example with FFmpeg `apad`) so its duration covers the storyboard. Keep fades after the last spoken syllable. The compositor checks media coverage and fails rather than silently writing a shorter export. To create a deliberately silent video, pass `--silent`.

## Conditional mask repairs

Use these only when inspection finds a specific artifact. Preserve the original matte and write repairs to another file.

Isolated furniture or objects can be removed with largest-component cleanup for a single presenter:

```bash
python3 "$SKILL_DIR/scripts/clean_mask.py" --mode components --mask work/person-mask.mkv --duration DURATION --out work/person-mask-components.mkv
```

Do not use largest-component selection indiscriminately with multiple people, separated hands, or props the user wants retained. The helper pools and dilates around the selected silhouette to preserve small fingers.

A static background object connected to the person matte can require local reference subtraction:

```bash
python3 "$SKILL_DIR/scripts/clean_mask.py" --mode reference --mask work/person-mask.mkv --source SOURCE.mov --duration DURATION --roi X Y WIDTH HEIGHT --reference-time EMPTY_REFERENCE_SECONDS --out work/person-mask-local.mkv
```

Coordinates refer to the fitted output canvas. The reference time is absolute source time; the ROI must be free of the presenter there. It suppresses pixels similar to that static background inside the ROI while retaining changed foreground, leaving the matte elsewhere intact. It assumes a fixed camera. Tune `--difference-low` / `--difference-high` for actual lighting; similar-colored foreground may need protection. `--preserve-cool-dark` is an optional navy-clothing heuristic, useful only after checking the footage's colors. It is not a universal mask setting.

In the original edit, a cup connected to a table survived segmentation. A broad lower-left exclusion rectangle also clipped a lowered hand briefly. The successful correction used a small empty-background reference region plus protection for dark clothing. For new footage, derive the region, reference time, and colors again. Check the full motion through any repair region, including just before/after a sampled frame; a safe still does not establish safety for the shot.

## Final checks

Inspect scene transitions and each reveal against the actual narration; check rapid gestures, glasses, hair, low hands, and the end of the clip. Watch/listen to the result when available, check loudness without clipping, and decode the full MP4:

```bash
ffmpeg -v error -i outputs/final.mp4 -f null -
```

If `ffmpeg` is not on PATH, use the discovered executable. No decoding errors confirms file integrity, not perceptual quality. Do not claim to have listened or watched when only numerical checks were possible. Deliver the actual finished MP4 and keep an editable storyboard when useful.
