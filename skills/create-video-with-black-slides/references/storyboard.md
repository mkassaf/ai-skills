# Event-driven storyboard

All times are seconds on the final narration timeline. `duration` is the final out point, not the original media length. Use continuous scenes covering `[0, duration]`; graphics are black between visible elements. Use enough time to read each label and reveal it with the corresponding phrase.

```json
{
  "title": "A new topic",
  "width": 1280,
  "height": 720,
  "fps": 30,
  "duration": 6,
  "fade_in": 0.35,
  "fade_out": 0.45,
  "scenes": [{
    "start": 0,
    "end": 6,
    "events": [
      {"kind":"text", "at":0.3, "x":64, "y":80, "text":"Start with a goal", "font":"clean", "bold":true, "size":40, "color":"white", "max_width":540},
      {"kind":"node", "at":1, "x":64, "y":240, "w":210, "h":90, "text":"Goal", "size":32, "color":"mint"},
      {"kind":"path", "at":2.5, "points":[[286,285],[350,285]], "color":"purple", "width":3, "arrow":true},
      {"kind":"node", "at":3.2, "x":364, "y":240, "w":210, "h":90, "text":"Plan", "size":32, "color":"purple"}
    ]
  }]
}
```

Canvas width and height must be positive even integers. The helpers default to 1280×720 at 30 fps. Use the same dimensions and frame rate for graphics, matte, and composite. Font sizes and coordinates are pixels; a different canvas needs a deliberate layout adjustment.

Events:

- Common: `kind`, absolute `at`, optional `end` (defaults to scene end), and optional `duration` for reveal length. Reveal defaults are about 0.55–0.65s. Colors may be palette names, `#RRGGBB`, or RGB/RGBA channel arrays.
- `text`: `x`, `y`, `text`; optional `size` (30), `font` (`hand` or `clean`), `bold`, `align` (`left`, `center`, `right`), `color`, `max_width`. `x` is the chosen alignment anchor. `y` is the top of the visible lettering. Use separate events for multiple lines. Text reveals horizontally, and overflow raises an error.
- `path`: `points` as `[x,y]` pairs; optional stroke `width` (3), `color`, and `arrow`. Paths draw progressively by length. Use paths for diagrams and line icons.
- `box`: `x`, `y`, `w`, `h`; optional stroke `width`, `color`. A slightly softened rectangular marker outline.
- `node`: box fields plus `text`, optional `size`, `font`, `bold`, `text_color`. Its centered label follows the outline.

Default palette: `mint` #89efda, `purple` #baa5ff, `white` #eef2f6, `muted` #9ca7b3, `dim` #43525d. Override colors through a top-level `palette` object when the user wants another treatment. The renderer uses macOS fonts when available, with a Linux sans-serif fallback; pass `--font-hand` and `--font-clean` for explicit TTF files. Recheck text widths when fonts change.

The large bundled Agentic AI example is executable data, not instructions or a fixed future script. Its serialized text positions already include centering offsets. For new nodes, use the `node` convenience event instead of manually calculating label positions.
