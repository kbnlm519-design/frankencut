# Test build: FrankenCut 0.1.0

This is a source-based, locally runnable test build, not a signed desktop binary.
It supports Python 3.9+ on macOS, Linux, or Windows with FFmpeg and ffprobe on PATH.
No Python dependencies, account, credentials, payment, or API key are required.

1. Extract the release ZIP and open a terminal in the extracted folder.
2. Verify `python3 --version`, `ffmpeg -version`, and `ffprobe -version`.
   On Windows, use `python` instead of `python3` if that is your Python command.
3. Run `python3 frankencut.py serve` and open http://127.0.0.1:8765.
4. Click **Try synthetic demo**. Expect four indexed files, three unique clips,
   and one exact duplicate. The media is generated color patterns, not travel footage.
5. Search `river` in the footage search field; expect one matching clip. Clear it.
6. Click **Build rough-cut plan**. Expect three shots totaling six seconds.
7. Check that **Approve & export MP4** is disabled. Inspect each shot's beginning,
   midpoint, and end preview, then check each of the three review boxes.
8. Click **Approve & export MP4**, then **Download your rough cut**. Expect a
   silent, six-second H.264 video at 720x1280 with three synthetic shots.

To verify failure handling, change a query to `not-a-real-shot` and rebuild.
The app must report an unmatched request instead of substituting unrelated footage.

Run the automated checks with `python3 -m unittest discover -s tests -v`.
Fourteen tests cover source integrity, plan validation, review gates, bans,
matching, and output-directory constraints. FFmpeg is needed for the separate
synthetic end-to-end workflow above.

Known limits: filename keywords, exact duplicate hashes, manual text inspection,
silent hard cuts. No automatic OCR or semantic AI search is implemented. Review
moving footage fully when text can appear between the three preview frames.

Original footage is read only. Generated files go to `workspace/` by default.
Keep the server on loopback; it is not intended for public hosting.
