---
inclusion: always
---

# FrankenCut

Build a small local-first tool for travel-video editors. The first working
version scans a folder, indexes metadata and exact duplicates, matches an English
shot list against filenames, previews the exact selected intervals, and exports
a reviewed rough cut through FFmpeg.

Never modify original footage. Exclude generated-output folders, including
`样片输出`, from ingestion. Do not upload footage to a cloud service. Rendering
must require explicit human approval and a text review of every selected shot.
Do not represent a filename keyword matcher as semantic AI, or manual text review
as automatic OCR. Those are future features.

Keep commands portable, avoid shell interpolation, bind the UI to loopback only,
and validate every render interval against the indexed source and its SHA-256.
Use only original synthetic demo footage in automated checks.

