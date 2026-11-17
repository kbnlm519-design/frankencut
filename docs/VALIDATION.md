# Validation

Date: 2026-11-17. All media checks used original synthetic FFmpeg color patterns.
No private source footage was ingested or uploaded.

- Python and JavaScript syntax checks passed.
- Unit checks cover matching failures, duplicate exclusion, source changes,
  approval gates, stale intervals, numeric validation, source boundaries,
  SHA/path ban lists, TK output-root constraints, generated-folder exclusion,
  and single-snapshot plan validation.
- A real FFmpeg run indexed four files into three unique clips plus one exact
  duplicate, generated nine interval previews, blocked an unreviewed export,
  then exported a reviewed three-shot video.
- ffprobe confirmed H.264 at 720x1280, duration 6.000 seconds, with no audio stream.
- Browser testing confirmed filename search (`river`), a three-shot plan,
  disabled export until all review checkboxes were selected, and a successful
  download link and playback element after export.
- Live HTTP checks returned 403 for cross-origin writes, missing-Origin writes,
  and an unexpected Host header; an arbitrary source-file URL returned 404.
- Browser testing uncovered an overly broad cross-site check on top-level GET
  navigation. It was corrected while retaining strict same-origin POST checks.
- Kiro CLI completed a source review; its accepted plan-snapshot change and
  verification are described in `KIRO_USAGE.md`.

Known limitations: metadata and exact hashes only; filename keyword search;
manual text inspection; silent hard-cut exports; no automatic OCR, semantic
search, music, captions, scene detection, or completed competition demo video.

