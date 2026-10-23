# Transcript-to-storyboard guide

Use this guide to turn a **timed, verified transcript** into the JSON consumed by `scripts/render_slides.py`. The transcript is the source of truth for the spoken claims; slide wording may simplify a claim but must not add one.

## 1. Align the narration

1. Find the actual audio duration and listen to the recording. Automatic transcripts can mishear names, prices, and technical terms; correct those before storyboarding.
2. Add timestamps at each change of idea. Word-level timing is useful for card reveals; a 2–5 second phrase-level alignment is enough for scene boundaries.
3. Keep `duration` equal to the audible narration length, rounded up only enough to avoid cutting off the last word. Every scene uses absolute seconds on this same timeline. Scenes should cover `[0, duration]` continuously, without overlaps or gaps.
4. If there is only a written transcript, obtain or produce a narration track before final timing. Make a provisional beat map from the text, then revise all timestamps against the recorded voice. A silent preview can be made first, but it is not a finished narrated video.

## 2. Choose visual beats

Make one scene for one spoken idea. A useful pattern for a short explainer is: hook with presenter → one full-screen example or process → presenter for interpretation → full-screen demonstration or choice → presenter for closing. Adapt the pattern to the actual transcript.

- Use `layout: "pip"` while the speaker introduces, bridges, qualifies, or wraps up an idea. Reserve the lower-right presenter area: keep the headline and cards in the left portion of the slide.
- Use `layout: "full"` when a process, sequence, comparison, or important decision needs the entire frame. The presenter should disappear for the whole beat, with a short fade at both boundaries.
- When no presenter video is available, make every scene `full`; `pip` reserves an empty box in the slide design.
- Put each card's `start` at the phrase that names its idea, or just after it. Do not reveal the answer before the speaker says it.
- A headline should be about 3–7 words; a subhead about one short sentence; a card title 1–3 words and body one brief phrase. Break a complex sentence into sequential cards rather than shrinking the type.
- Put stable labels on screen long enough to read. Roughly 2–3 seconds for a short card is a useful minimum, and longer for a comparison or diagram.
- Use a `callout` only for the scene's takeaway. It should reinforce the narrated point rather than introduce a new claim.

## 3. Populate the storyboard JSON

Top level:

| Field | Meaning |
| --- | --- |
| `title` | Short topic label in the top-left masthead. |
| `duration` | Total narrated seconds. |
| `scenes` | Ordered, continuous scenes. |

Scene fields:

| Field | Meaning |
| --- | --- |
| `start`, `end` | Absolute seconds on the final audio timeline. |
| `layout` | `pip` for presenter inset or `full` to hide the presenter. |
| `section` | Short all-caps editorial section label, such as `THE PROCESS`. |
| `headline` | Main idea of this beat. |
| `subhead` | Optional short clarifying line. |
| `cards` | Ordered list of reveal cards; each has `start`, `title`, `body`, and `accent`. |
| `callout` | Optional short takeaway string. |

Card `start` is **absolute video time**, not time relative to the scene. It must fall within that scene. Use `violet` for a goal or main point, `cobalt` for an action or tool, `orange` for review or a trade-off, and `cranberry` for a conflict. Color communicates the role of the idea; it should not be changed randomly from one card to the next.

The renderer implements the finished video's visual language: warm ivory and lightly tinted backgrounds, faint grid, dark ink typography, white rounded cards, colored left rails, gentle fade-and-rise entrances, and a thin animated timeline. Keep the video at 1280×720 and 30 fps for the matching presenter treatment. The presenter-based example is in [`example-storyboard.json`](example-storyboard.json). Its illustrative voice track says: **0–7 s** a lost device can put a sole copy at risk, while a backup keeps another copy; **7–20 s** selected files are saved, later changes are copied, and files can be restored; **20–29 s** the person chooses which files and how often to back them up. Replace every line and timestamp for a real project.

## 4. Review against the voice

Before final export, inspect a frame just after each scene begins, at each card reveal, and just before every presenter hide/show boundary. Watch the full composite with sound. Confirm that words are readable on a phone, no card overlaps the presenter, the speaker disappears only during intended full-screen beats, and the last spoken syllable is not clipped. If a slide paraphrase could be heard as a stronger claim than the narration, rewrite it.
