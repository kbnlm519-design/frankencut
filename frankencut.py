#!/usr/bin/env python3
"""FrankenCut: local footage indexing and a human-reviewed rough-cut pipeline."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
EXCLUDED = {".git", "__pycache__", "workspace", "output", "outputs", "renders", "样片输出"}
LOCK = threading.Lock()


def run(args):
    try:
        return subprocess.run([str(x) for x in args], check=True, capture_output=True,
                              text=True, timeout=600).stdout
    except FileNotFoundError as exc:
        raise ValueError("Install FFmpeg and make ffmpeg / ffprobe available on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError((exc.stderr or str(exc))[-1500:]) from exc


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def number(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label + " must be a number.")
    if not math.isfinite(value) or value < minimum:
        raise ValueError(label + " must be finite and at least " + str(minimum))
    return float(value)


def inside(path, parent):
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def preview(source, start, seconds, prefix, workspace):
    folder = workspace / "thumbnails"
    folder.mkdir(parents=True, exist_ok=True)
    images = []
    # Stay just inside the final selected frame, rather than seeking beyond it.
    for i, offset in enumerate((0, seconds / 2, max(0, seconds - 0.08))):
        name = prefix + "-" + str(i) + ".jpg"
        target = folder / name
        if not target.exists():
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss",
                 start + offset, "-i", source, "-frames:v", "1", "-vf",
                 "scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2",
                 target])
        if not target.is_file():
            raise ValueError("Could not create an interval preview for " + str(source))
        images.append("/thumbnails/" + name)
    return images


def scan(folder, workspace):
    if not isinstance(folder, (str, Path)) or not str(folder).strip():
        raise ValueError("Choose a footage folder first.")
    folder = Path(folder).expanduser().resolve()
    workspace = Path(workspace).resolve()
    if not folder.is_dir():
        raise ValueError("Choose an existing footage folder.")
    if folder == workspace or inside(folder, workspace):
        raise ValueError("The footage folder must be outside the generated workspace.")
    if "样片输出" in folder.parts:
        raise ValueError("Generated sample outputs cannot be indexed as raw footage.")
    for ancestor in (folder, *folder.parents):
        if ancestor.name == "TK原素材" and not inside(workspace, ancestor / "样片输出"):
            raise ValueError("For TK footage, set --workspace inside " + str(ancestor / "样片输出"))
    assets, errors, seen = [], [], {}
    for directory, subdirs, files in os.walk(folder, followlinks=False):
        subdirs[:] = sorted(d for d in subdirs if d not in EXCLUDED
                            and not (Path(directory) / d).is_symlink()
                            and not inside(Path(directory) / d, workspace))
        for filename in sorted(files):
            source = Path(directory) / filename
            if source.suffix.lower() not in EXTENSIONS or source.is_symlink():
                continue
            try:
                data = json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                                       "-of", "json", source]))
                video = next(s for s in data["streams"] if s.get("codec_type") == "video")
                seconds = number(float(data["format"].get("duration", 0)), "Source duration", .1)
                sha = digest(source)
                item = {"id": uuid.uuid5(uuid.NAMESPACE_URL, str(source)).hex,
                        "path": str(source), "name": str(source.relative_to(folder)),
                        "duration": seconds, "width": video["width"], "height": video["height"],
                        "sha256": sha, "duplicate_of": seen.get(sha),
                        "thumbnails": preview(source, 0, seconds, sha[:24], workspace)}
                seen.setdefault(sha, item["name"])
                assets.append(item)
            except (ValueError, KeyError, StopIteration, OSError) as exc:
                errors.append({"name": str(source.relative_to(folder)), "error": str(exc)})
    result = {"root": str(folder), "assets": assets, "errors": errors}
    save(workspace / "library.json", result)
    return result


def score(query, name):
    tokens = re.findall(r"\w+", query.casefold())
    title = name.casefold()
    return sum(1 for word in tokens if word in title)


def make_plan(library, requests, workspace):
    if not isinstance(requests, list) or not 1 <= len(requests) <= 30:
        raise ValueError("Use a shot list with 1 to 30 requests.")
    used, shots = set(), []
    for request in requests:
        if not isinstance(request, dict):
            raise ValueError("Each shot request must be an object.")
        query = request.get("query", "")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Each request needs a non-empty filename keyword query.")
        candidates = [a for a in library["assets"] if not a["duplicate_of"] and a["id"] not in used]
        candidates = sorted(candidates, key=lambda a: (-score(query, a["name"]), a["name"]))
        if not candidates or score(query, candidates[0]["name"]) == 0:
            raise ValueError("No unused footage matches: " + query + ". Rename/tag filenames or revise the shot list.")
        asset = candidates[0]
        start = number(request.get("start", 0), "Start")
        seconds = number(request.get("seconds", 2), "Seconds", .2)
        if start + seconds > asset["duration"] + .001:
            raise ValueError("Shot exceeds source duration: " + asset["name"])
        if seconds > 30:
            raise ValueError("Each shot is limited to 30 seconds in this prototype.")
        key = hashlib.sha256((asset["sha256"] + repr((start, seconds))).encode()).hexdigest()[:24]
        shots.append({"asset_id": asset["id"], "name": asset["name"], "source_sha": asset["sha256"],
                      "query": query, "start": start, "seconds": seconds, "text_review": "pending",
                      "thumbnails": preview(asset["path"], start, seconds, key, workspace)})
        used.add(asset["id"])
    result = {"version": 1, "shots": shots, "total_seconds": sum(s["seconds"] for s in shots)}
    save(workspace / "plan.json", result)
    return result


def ban_entries(value):
    """Read nested lists/dicts containing SHA-256 values or absolute source paths."""
    hashes, paths = set(), set()
    def visit(node):
        if isinstance(node, dict):
            for key, entry in node.items():
                if re.fullmatch(r"[a-fA-F0-9]{64}", str(key)):
                    hashes.add(str(key).lower())
                visit(entry)
        elif isinstance(node, list):
            for entry in node:
                visit(entry)
        elif isinstance(node, str):
            if re.fullmatch(r"[a-fA-F0-9]{64}", node):
                hashes.add(node.lower())
            elif Path(node).is_absolute():
                paths.add(str(Path(node).resolve()))
    visit(value)
    return hashes, paths


def validate_plan(plan, library, workspace):
    if not isinstance(plan, dict) or not isinstance(plan.get("shots"), list) or not 1 <= len(plan["shots"]) <= 30:
        raise ValueError("Invalid or empty plan.")
    assets = {a["id"]: a for a in library["assets"]}
    # Use one plan snapshot for the entire validation, including CLI exports.
    saved = load(workspace / "plan.json")
    approved_intervals = {s["asset_id"]: (s["start"], s["seconds"]) for s in saved["shots"]}
    validated, banfiles = [], {workspace / "bans.json"}
    for shot in plan["shots"]:
        if not isinstance(shot, dict):
            raise ValueError("Invalid shot.")
        asset = assets.get(shot.get("asset_id"))
        if asset is None:
            raise ValueError("Unknown asset: rescan and rebuild the plan.")
        source = Path(asset["path"])
        if source.is_symlink() or not source.is_file() or not inside(source, library["root"]):
            raise ValueError("Source is missing or outside the scanned library.")
        start = number(shot.get("start"), "Start")
        seconds = number(shot.get("seconds"), "Seconds", .2)
        if seconds > 30 or start + seconds > asset["duration"] + .001:
            raise ValueError("Invalid source interval.")
        if shot.get("text_review") != "pass":
            raise ValueError("Review all three interval frames and approve every shot before export.")
        if shot.get("source_sha") != asset["sha256"] or digest(source) != asset["sha256"]:
            raise ValueError("Source changed after indexing: rescan and review again.")
        # Preview timestamps are regenerated from the approved interval by the UI;
        # prevent CLI/API edits from reusing an old interval's review.
        if (start, seconds) != approved_intervals.get(shot["asset_id"]):
            raise ValueError("Interval changed: rebuild the plan and inspect new previews.")
        for ancestor in source.parents:
            banfiles.add(ancestor / "素材禁用清单.json")
        validated.append((asset, start, seconds))
    for banfile in banfiles:
        if banfile.is_file():
            hashes, paths = ban_entries(load(banfile))
            for asset, _, _ in validated:
                if asset["sha256"] in hashes or str(Path(asset["path"]).resolve()) in paths:
                    raise ValueError("A selected source is on the ban list: " + asset["name"])
    return validated


def render(plan, library, workspace, approved=False):
    if not approved:
        raise ValueError("Explicit export approval is required.")
    validated = validate_plan(plan, library, workspace)
    exports = workspace / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    result = exports / ("frankencut-" + uuid.uuid4().hex[:12] + ".mp4")
    filters = ("scale=720:1280:force_original_aspect_ratio=decrease,"
               "pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30,format=yuv420p")
    with tempfile.TemporaryDirectory(dir=workspace) as temporary:
        segments = []
        for index, (asset, start, seconds) in enumerate(validated):
            target = Path(temporary) / (str(index) + ".mp4")
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", start,
                 "-i", asset["path"], "-t", seconds, "-an", "-vf", filters,
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", target])
            segments.append(target)
        listing = Path(temporary) / "segments.txt"
        # Temporary segment basenames are generated integers, never source filenames.
        listing.write_text("".join("file '" + p.name + "'\n" for p in segments), encoding="utf-8")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "1",
             "-i", listing, "-c", "copy", "-movflags", "+faststart", result])
    save(result.with_suffix(".json"), plan)
    return {"path": str(result), "url": "/exports/" + result.name}


def demo(workspace):
    source = workspace.parent / "demo-footage"
    source.mkdir(parents=True, exist_ok=True)
    for name, effect in (("city-night", "hue=h=0"), ("river-walk", "hue=h=110"),
                         ("mountain-sunrise", "hue=h=220")):
        target = source / (name + ".mp4")
        if not target.exists():
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                 "testsrc2=size=640x360:rate=30:duration=4", "-vf", effect, "-an", "-c:v",
                 "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", target])
    shutil.copyfile(source / "city-night.mp4", source / "copy-city-night.mp4")
    library = scan(source, workspace)
    return {"folder": str(source), "library": library}


def serve(workspace, port):
    workspace.mkdir(parents=True, exist_ok=True)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def reply(self, value, status=200):
            payload = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def trusted(self):
            hosts = {"127.0.0.1:" + str(port), "localhost:" + str(port)}
            return self.headers.get("Host") in hosts

        def do_GET(self):
            if not self.trusted():
                return self.reply({"error": "Local requests only."}, 403)
            path = urlparse(self.path).path
            if path == "/api/state":
                library = load(workspace / "library.json") if (workspace / "library.json").is_file() else {"assets": [], "errors": []}
                return self.reply({"library": library})
            static = {"/": ROOT / "web/index.html", "/app.js": ROOT / "web/app.js", "/style.css": ROOT / "web/style.css"}
            target = static.get(path)
            if target is None and re.fullmatch(r"/thumbnails/[a-zA-Z0-9-]+\.jpg", path):
                target = workspace / path.lstrip("/")
            if target is None and re.fullmatch(r"/exports/frankencut-[a-f0-9]+\.mp4", path):
                target = workspace / path.lstrip("/")
            if target is None or not target.is_file():
                return self.reply({"error": "Not found."}, 404)
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            with target.open("rb") as stream:
                shutil.copyfileobj(stream, self.wfile)

        def do_POST(self):
            origin = self.headers.get("Origin")
            if not self.trusted() or self.headers.get("Sec-Fetch-Site") == "cross-site" or origin not in ("http://127.0.0.1:" + str(port), "http://localhost:" + str(port)):
                return self.reply({"error": "Same-origin requests only."}, 403)
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.reply({"error": "JSON required."}, 400)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 100000:
                    raise ValueError("Invalid request size.")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("Request must be an object.")
                with LOCK:
                    if self.path == "/api/demo":
                        result = demo(workspace)
                    elif self.path == "/api/scan":
                        result = {"library": scan(payload.get("folder", ""), workspace)}
                    elif self.path == "/api/plan":
                        result = make_plan(load(workspace / "library.json"), payload.get("shots"), workspace)
                    elif self.path == "/api/render":
                        result = render(payload.get("plan"), load(workspace / "library.json"), workspace,
                                        approved=payload.get("approved") is True)
                    else:
                        return self.reply({"error": "Not found."}, 404)
                self.reply(result)
            except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
                self.reply({"error": str(exc)}, 400)
    print("FrankenCut: http://127.0.0.1:" + str(port), flush=True)
    print("Local footage stays on this computer. Ctrl+C to stop.", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=ROOT / "workspace")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Generate original synthetic footage and index it.")
    index = commands.add_parser("scan", help="Index footage without changing original files.")
    index.add_argument("folder")
    planner = commands.add_parser("plan", help="Build a reviewed-later shot plan from JSON.")
    planner.add_argument("shotlist", type=Path)
    commands.add_parser("render", help="Render plan.json after reviewing all shots.").add_argument("--approve", action="store_true")
    web = commands.add_parser("serve", help="Open the local dashboard.")
    web.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    try:
        if args.command == "serve":
            serve(workspace, args.port)
            return
        if args.command == "demo":
            result = demo(workspace)
        elif args.command == "scan":
            result = scan(args.folder, workspace)
        elif args.command == "plan":
            result = make_plan(load(workspace / "library.json"), load(args.shotlist), workspace)
        else:
            result = render(load(workspace / "plan.json"), load(workspace / "library.json"), workspace, args.approve)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, "Error: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
