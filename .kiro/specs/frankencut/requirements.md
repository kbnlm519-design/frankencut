# Requirements

1. A user can index local MP4, MOV, MKV, WEBM, and M4V files recursively.
2. Each asset shows duration, dimensions, SHA-256, three thumbnails, and exact
   duplicate status. Generated-output directories are excluded.
3. An English shot list matches filename keywords. Unmatched requests must be
   reported, never silently replaced by unrelated footage.
4. Every planned shot has explicit in/out times and previews at the beginning,
   midpoint, and end of that actual interval.
5. Export is blocked until the user approves each shot's text review. Changed
   sources and paths or hashes in a supported local ban list are rejected.
6. FFmpeg exports a 720x1280 H.264 rough cut. Landscape footage is fitted with
   letterboxing so the app does not silently crop away meaningful content.
7. The local web UI never uploads footage, exposes arbitrary files, or accepts
   cross-origin write requests. Original audio is omitted in this first version.
8. README documents implemented features, limitations, and actual tool usage.

