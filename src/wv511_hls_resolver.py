#!/usr/bin/env python3
# =============================================================================
# FILE: src/wv511_hls_resolver.py
# PURPOSE:
#   Resolve WV511 camera HLS URLs from route pages + flowplayer pages.
#
# SCOPE:
#   - deterministic
#   - minimal
#   - safe overwrite of the broken resolver
#   - supports route filter and camera-name filter
#   - writes per-camera JSON reports and summary JSON
#   - optionally validates with cv2 if available
#
# NOTES:
#   - Crosslanes is CAM022, not CAM082
#   - route page may contain many cameras; camera title match is name-based
# =============================================================================

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import requests

try:
    import cv2  # type: ignore
except Exception:
    cv2 = None


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "cameras.json"
REPORT_DIR = ROOT / "data" / "resolver_reports"
ROUTE_HTML_DIR = ROOT / "data" / "route_pages"
FLOWPLAYER_DIR = ROOT / "data" / "flowplayer_probe"

HEADERS = {"User-Agent": "Mozilla/5.0"}

MYCAMS_RE = re.compile(r'myCams\[(\d+)\]\s*=\s*"((?:[^"\\]|\\.)*)";', re.I)
HLS_RE = re.compile(r"https://[^'\"\\s]+/rtplive/CAM\d{3,}/playlist\.m3u8", re.I)


@dataclass
class CameraReport:
    name: str
    route: str
    county: str
    page_url: str
    matched: bool
    matched_title: str
    resolved_camid: str
    resolved_from: str
    stream_url: str
    validated: bool
    validation: dict[str, Any]
    notes: list[str]


def slugify(value: str) -> str:
    s = value.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "item"


def ensure_dirs() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ROUTE_HTML_DIR.mkdir(parents=True, exist_ok=True)
    FLOWPLAYER_DIR.mkdir(parents=True, exist_ok=True)


def fetch_text(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(data: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def route_page_url(route: str) -> str:
    return f"https://www.wv511.org/CameraListing.aspx?ROUTE={route}"


def flowplayer_url(camid: str) -> str:
    return f"https://www.wv511.org/flowplayeri.aspx?CAMID={camid}"


def normalize_title_for_match(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^\s*I-64:\s*\[[A-Z]+\]", "", s, flags=re.I)
    s = re.sub(r"^\s*I-64\s*", "", s, flags=re.I)
    s = re.sub(r"\bMM\s+", "@ ", s, flags=re.I)
    s = s.replace("exit(", "exit (")
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def parse_mycams(html: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for _, raw in MYCAMS_RE.findall(html):
        val = raw.encode("utf-8").decode("unicode_escape")
        parts = val.split("|")
        while len(parts) < 7:
            parts.append("")
        entries.append(
            {
                "title": parts[0].strip(),
                "image": parts[2].strip(),
                "camid": parts[3].strip(),
                "flag1": parts[4].strip(),
                "flag2": parts[5].strip(),
                "flag3": parts[6].strip(),
                "raw": val,
            }
        )
    return entries


def extract_hls_from_flowplayer_html(html: str) -> str | None:
    m = HLS_RE.search(html)
    if m:
        return m.group(0)

    fallback_patterns = [
        r"""hls\.loadSource\(['"](?P<url>https://[^'"]+/rtplive/CAM\d{3,}/playlist\.m3u8)['"]\)""",
        r"""<source[^>]+src=['"](?P<url>https://[^'"]+/rtplive/CAM\d{3,}/playlist\.m3u8)['"]""",
        r"""(?P<url>https://[^'"]+/rtplive/CAM\d{3,}/playlist\.m3u8)""",
    ]

    for pattern in fallback_patterns:
        m = re.search(pattern, html, re.I)
        if m:
            return m.group("url") if "url" in m.groupdict() else m.group(0)

    return None


def validate_stream(url: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not url:
        return result
    if cv2 is None:
        result["cv2_available"] = False
        return result

    cap = cv2.VideoCapture(url)
    result["opened"] = bool(cap.isOpened())
    if cap.isOpened():
        ok, frame = cap.read()
        result["first_frame_ok"] = bool(ok)
        result["shape"] = None if frame is None else list(frame.shape)
        result["fps"] = float(cap.get(cv2.CAP_PROP_FPS))
        result["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        result["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return result


def choose_match(camera_name: str, entries: list[dict[str, str]]) -> dict[str, str] | None:
    target = normalize_title_for_match(camera_name)

    exact = []
    contains = []

    for entry in entries:
        title_norm = normalize_title_for_match(entry["title"])
        if title_norm == target:
            exact.append(entry)
        elif target in title_norm or title_norm in target:
            contains.append(entry)

    if exact:
        return exact[0]
    if contains:
        return contains[0]
    return None


def process_camera(
    cam: dict[str, Any],
    route_html_cache: dict[str, str],
    refresh_route_pages: bool,
) -> CameraReport:
    name = str(cam.get("name", "")).strip()
    route = str(cam.get("route", "")).strip()
    county = str(cam.get("county", "")).strip()
    page_url = str(cam.get("page_url", "")).strip() or route_page_url(route)

    notes: list[str] = []
    matched = False
    matched_title = ""
    resolved_camid = str(cam.get("resolved_camid", "") or "").strip()
    resolved_from = str(cam.get("resolved_from", "") or "").strip()
    stream_url = str(cam.get("stream_url", "") or "").strip()
    validated = False
    validation: dict[str, Any] = {}

    if route not in route_html_cache or refresh_route_pages:
        html = fetch_text(route_page_url(route))
        route_html_cache[route] = html
        (ROUTE_HTML_DIR / f"{slugify(route)}.html").write_text(html, encoding="utf-8")
    else:
        html = route_html_cache[route]

    entries = parse_mycams(html)
    match = choose_match(name, entries)
    if match is None:
        notes.append("camera title not found in route page myCams array")
        return CameraReport(
            name=name,
            route=route,
            county=county,
            page_url=page_url,
            matched=False,
            matched_title="",
            resolved_camid=resolved_camid,
            resolved_from=resolved_from,
            stream_url=stream_url,
            validated=False,
            validation=validation,
            notes=notes,
        )

    matched = True
    matched_title = match["title"]
    resolved_camid = match["camid"]
    resolved_from = flowplayer_url(resolved_camid)

    fp_html = fetch_text(resolved_from)
    (FLOWPLAYER_DIR / f"{resolved_camid.lower()}_body.txt").write_text(
        fp_html, encoding="utf-8"
    )

    found_hls = extract_hls_from_flowplayer_html(fp_html)
    if found_hls:
        stream_url = found_hls
        validation = validate_stream(stream_url)
        validated = bool(validation.get("opened")) and bool(validation.get("first_frame_ok"))
    else:
        notes.append("no hls url found in flowplayer html")

    return CameraReport(
        name=name,
        route=route,
        county=county,
        page_url=page_url,
        matched=matched,
        matched_title=matched_title,
        resolved_camid=resolved_camid,
        resolved_from=resolved_from,
        stream_url=stream_url,
        validated=validated,
        validation=validation,
        notes=notes,
    )


def update_config_from_reports(config: dict[str, Any], reports: list[CameraReport]) -> None:
    by_name = {r.name: r for r in reports}
    for cam in config.get("cameras", []):
        r = by_name.get(str(cam.get("name", "")).strip())
        if not r:
            continue
        cam["resolved_camid"] = r.resolved_camid
        cam["resolved_from"] = r.resolved_from
        cam["stream_url"] = r.stream_url


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--route", default="", help="Route filter, example: I-64")
    p.add_argument("--camera", default="", help='Camera name filter, example: "I-64 @ 47 Crosslanes"')
    p.add_argument("--refresh-route-pages", action="store_true")
    p.add_argument("--report-only", action="store_true")
    return p


def main() -> int:
    ensure_dirs()
    args = build_parser().parse_args()

    config = load_config()
    cameras = list(config.get("cameras", []))

    if args.route:
        cameras = [c for c in cameras if str(c.get("route", "")).strip().lower() == args.route.strip().lower()]

    if args.camera:
        cameras = [c for c in cameras if str(c.get("name", "")).strip().lower() == args.camera.strip().lower()]

    route_html_cache: dict[str, str] = {}
    reports: list[CameraReport] = []

    for cam in cameras:
        report = process_camera(
            cam=cam,
            route_html_cache=route_html_cache,
            refresh_route_pages=args.refresh_route_pages,
        )
        reports.append(report)

        report_path = REPORT_DIR / f"{slugify(report.name)}.json"
        report_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")

        if report.stream_url:
            print(f"[RESOLVED] {report.name}: {report.resolved_camid} -> {report.stream_url}")
        else:
            note = "; ".join(report.notes) if report.notes else "unresolved"
            print(f"[UNRESOLVED] {report.name}: {report.resolved_camid or 'NO_CAMID'} :: {note}")

    if not args.report_only:
        update_config_from_reports(config, reports)
        save_config(config)

    summary = {
        "selected_count": len(reports),
        "resolved_count": sum(1 for r in reports if bool(r.stream_url)),
        "unresolved_count": sum(1 for r in reports if not r.stream_url),
        "report_only": bool(args.report_only),
        "validated": True,
        "route_filter": args.route,
        "camera_filter": args.camera,
        "reports": [f"{slugify(r.name)}.json" for r in reports],
    }

    (REPORT_DIR / "_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\nSUMMARY")
    print(f"selected={summary['selected_count']}")
    print(f"resolved={summary['resolved_count']}")
    print(f"unresolved={summary['unresolved_count']}")
    print(f"summary_file={REPORT_DIR / '_summary.json'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# =============================================================================
# INSTRUCTIONS
#
# chmod +x /home/pc-10/Downloads/traffic_recorder_project/src/wv511_hls_resolver.py
#
# Compile check:
# python3 -m py_compile /home/pc-10/Downloads/traffic_recorder_project/src/wv511_hls_resolver.py
#
# Single camera run:
# cd /home/pc-10/Downloads/traffic_recorder_project && source .venv/bin/activate && \
# PYTHONPATH="$PWD" python -m src.wv511_hls_resolver --route I-64 --camera "I-64 @ 47 Crosslanes" --refresh-route-pages
#
# Full route run:
# cd /home/pc-10/Downloads/traffic_recorder_project && source .venv/bin/activate && \
# PYTHONPATH="$PWD" python -m src.wv511_hls_resolver --route I-64 --refresh-route-pages
# =============================================================================
