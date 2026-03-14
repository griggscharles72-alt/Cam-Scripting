from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "cameras.json"
REPORT_DIR = ROOT / "data" / "resolver_reports"

MEDIA_PATTERNS = {
    "m3u8": re.compile(r'https?://[^\s\'"]+?\.m3u8[^\s\'"]*', re.I),
    "mpd": re.compile(r'https?://[^\s\'"]+?\.mpd[^\s\'"]*', re.I),
    "mp4": re.compile(r'https?://[^\s\'"]+?\.mp4[^\s\'"]*', re.I),
    "jpg": re.compile(r'https?://[^\s\'"]+?\.jpe?g[^\s\'"]*', re.I),
    "png": re.compile(r'https?://[^\s\'"]+?\.png[^\s\'"]*', re.I),
    "rtsp": re.compile(r'rtsp://[^\s\'"]+', re.I),
    "src_like": re.compile(r'''(?:src|href|data-[\w-]+)\s*=\s*["']([^"']+)["']''', re.I),
}

def load_cameras():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cameras", [])

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")

def uniq(items):
    out, seen = [], set()
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out

def extract(page_url: str, html: str):
    found = {}
    for key in ("m3u8", "mpd", "mp4", "jpg", "png", "rtsp"):
        found[key] = uniq(MEDIA_PATTERNS[key].findall(html))
    src_like = [urljoin(page_url, x) for x in MEDIA_PATTERNS["src_like"].findall(html)]
    found["src_like"] = uniq(src_like)
    found["interesting_src_like"] = [
        x for x in found["src_like"]
        if any(k in x.lower() for k in ("m3u8", "mpd", "mp4", "jpg", "jpeg", "png", "stream", "video", "camera", "player", "manifest", "playlist"))
    ]
    return found

def resolve_one(camera: dict):
    name = camera.get("name", "unknown")
    page_url = (camera.get("page_url") or "").strip()
    stream_url = (camera.get("stream_url") or "").strip()

    report = {
        "name": name,
        "route": camera.get("route"),
        "county": camera.get("county"),
        "page_url": page_url,
        "stream_url": stream_url,
        "http_status": None,
        "final_url": None,
        "content_type": None,
        "candidate_counts": {},
        "candidates": {},
        "notes": [],
    }

    if stream_url:
        report["notes"].append("stream_url already present in config")
        return report
    if not page_url:
        report["notes"].append("no page_url present")
        return report

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
    }

    try:
        r = requests.get(page_url, headers=headers, timeout=20)
        report["http_status"] = r.status_code
        report["final_url"] = r.url
        report["content_type"] = r.headers.get("Content-Type", "")
        candidates = extract(r.url, r.text)
        report["candidates"] = candidates
        report["candidate_counts"] = {k: len(v) for k, v in candidates.items()}
        direct_total = sum(len(candidates[k]) for k in ("m3u8", "mpd", "mp4", "jpg", "png", "rtsp"))
        if direct_total:
            report["notes"].append("direct media-like URLs found in HTML")
        else:
            report["notes"].append("no direct media-like URLs found in raw HTML")
        if candidates["interesting_src_like"]:
            report["notes"].append("interesting src/href/data references found")
        else:
            report["notes"].append("no interesting src/href/data references found")
    except Exception as e:
        report["notes"].append(f"request failed: {type(e).__name__}: {e}")

    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", required=True)
    args = parser.parse_args()

    cameras = load_cameras()
    matches = [c for c in cameras if c.get("name") == args.camera]
    if not matches:
        raise SystemExit(f"Camera not found: {args.camera}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = resolve_one(matches[0])
    out = REPORT_DIR / f"{slugify(report['name'])}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=" * 80)
    print(report["name"])
    print(f"page_url     : {report['page_url']}")
    print(f"http_status  : {report['http_status']}")
    print(f"final_url    : {report['final_url']}")
    print(f"content_type : {report['content_type']}")
    print(f"report_path  : {out}")
    print("candidate_counts:")
    for k, v in report["candidate_counts"].items():
        print(f"  - {k}: {v}")
    print("notes:")
    for note in report["notes"]:
        print(f"  - {note}")

if __name__ == "__main__":
    main()
