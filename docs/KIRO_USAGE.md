# Kiro usage record

## 2026-11-17 — Kiro CLI code review

The first implementation was built with Codex. Kiro CLI then performed an actual
noninteractive code review of `frankencut.py`, `web/app.js`,
`tests/test_pipeline.py`, and the requirements document. No media files,
credentials, or account details were provided in the review prompt.

Task: review material correctness of approval gates, source freshness, interval
previews, FFmpeg rendering, local HTTP boundaries, and generated-output exclusion;
provide concrete changes and useful regression tests. Tool execution was disabled
for the review session. The command finished successfully in approximately 52
seconds. Input SHA-256:
`541d7b332c7b95613eb555d59c8d398d5bf156e43c18a8c8824939325d510b75`.

### Accepted contribution

Kiro identified repeated reads of `plan.json` inside per-shot export validation.
The pipeline now loads one saved plan snapshot before the loop and uses a map of
approved intervals. A two-shot regression test verifies a single read, supporting
consistent validation across the complete export.

### Checked rather than blindly applied

Kiro also raised concerns about preview cache keys, missing-Origin handling,
nested-workspace ingestion, and concat paths. Inspection found that equivalent
floating-point timestamps represent the same interval, missing Origin already
fails the allowlist, workspace paths are explicitly pruned during traversal, and
concat basenames are generated integers. Those suggestions were not applied as
claimed defects. A nested-workspace regression check and live HTTP rejection
checks confirmed the existing behavior.

This record describes genuine Kiro use; it does not claim that Kiro authored the
entire application, that semantic search/OCR is implemented, or that the project
has already satisfied every final hackathon submission requirement.

