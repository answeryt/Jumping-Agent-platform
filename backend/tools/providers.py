from __future__ import annotations

import html
import json
import math
import os
import re
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from xml.etree import ElementTree


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = PROJECT_ROOT / "backend" / "artifacts" / "tools"


def _artifact_dir(tool_name: str) -> Path:
    path = ARTIFACT_ROOT / tool_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _timestamp_id() -> str:
    return str(int(time.time() * 1000))


def _read_url(url: str, *, timeout: int = 12) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(2 * 1024 * 1024)
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def _strip_html(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", value)
    text = re.sub(r"(?is)<.*?>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def default_web_search_provider(params: Dict[str, Any]) -> Dict[str, Any]:
    query = str(params.get("query") or "").strip()
    if not query:
        return {"status": "error", "error": "query required", "results": []}

    encoded = urllib.parse.urlencode({"q": query})
    search_url = f"https://duckduckgo.com/html/?{encoded}"
    try:
        body = _read_url(search_url)
    except Exception as exc:
        return {
            "status": "error",
            "provider": "duckduckgo_html",
            "query": query,
            "results": [],
            "error": f"web search request failed: {exc}",
        }

    results: List[Dict[str, str]] = []
    pattern = re.compile(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(body):
        title = _strip_html(match.group("title"))
        href = html.unescape(match.group("href"))
        if href.startswith("//duckduckgo.com/l/?"):
            parsed = urllib.parse.urlparse("https:" + href)
            target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
            href = urllib.parse.unquote(target) or href
        if title and href:
            results.append({"title": title, "url": href})
        if len(results) >= int(params.get("maxResults") or 5):
            break

    return {
        "status": "ok",
        "provider": "duckduckgo_html",
        "query": query,
        "results": results,
        "source": search_url,
    }


def _iter_input_paths(params: Dict[str, Any], single_key: str, list_key: str) -> List[Path]:
    values: List[str] = []
    single = params.get(single_key)
    if isinstance(single, str):
        values.append(single)
    many = params.get(list_key)
    if isinstance(many, list):
        values.extend(str(item) for item in many if isinstance(item, str))
    return [Path(value) for value in values if "://" not in value]


def _file_info(path: Path) -> Dict[str, Any]:
    stat = path.stat()
    return {"path": str(path), "exists": True, "sizeBytes": stat.st_size, "suffix": path.suffix.lower()}


def _png_size(data: bytes) -> Optional[Dict[str, int]]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return {"width": width, "height": height}
    return None


def _gif_size(data: bytes) -> Optional[Dict[str, int]]:
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return {"width": width, "height": height}
    return None


def _jpeg_size(data: bytes) -> Optional[Dict[str, int]]:
    if not data.startswith(b"\xff\xd8"):
        return None
    idx = 2
    while idx + 9 < len(data):
        if data[idx] != 0xFF:
            idx += 1
            continue
        marker = data[idx + 1]
        idx += 2
        if marker in (0xD8, 0xD9):
            continue
        if idx + 2 > len(data):
            return None
        segment_length = struct.unpack(">H", data[idx : idx + 2])[0]
        if marker in range(0xC0, 0xC4) and idx + 7 < len(data):
            height, width = struct.unpack(">HH", data[idx + 3 : idx + 7])
            return {"width": width, "height": height}
        idx += segment_length
    return None


def _svg_summary(path: Path) -> Dict[str, Any]:
    root = ElementTree.fromstring(path.read_text(encoding="utf-8", errors="replace"))
    texts = [" ".join((node.text or "").split()) for node in root.iter() if node.text and node.text.strip()]
    tags: Dict[str, int] = {}
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        tags[tag] = tags.get(tag, 0) + 1
    return {
        "width": root.attrib.get("width"),
        "height": root.attrib.get("height"),
        "text": [item for item in texts if item],
        "elements": tags,
    }


def default_image_provider(params: Dict[str, Any]) -> Dict[str, Any]:
    images = []
    for path in _iter_input_paths(params, "image", "images"):
        if not path.exists():
            images.append({"path": str(path), "exists": False, "error": "file not found"})
            continue
        info = _file_info(path)
        try:
            if path.suffix.lower() == ".svg":
                info["analysis"] = _svg_summary(path)
            else:
                data = path.read_bytes()[:256 * 1024]
                size = _png_size(data) or _gif_size(data) or _jpeg_size(data)
                if size:
                    info.update(size)
        except Exception as exc:
            info["warning"] = str(exc)
        images.append(info)
    return {
        "status": "ok",
        "provider": "local_image_metadata",
        "prompt": params.get("prompt"),
        "images": images,
    }


def _extract_pdf_text_with_library(path: Path, max_pages: int) -> Dict[str, Any]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except Exception as exc:
            return {"error": f"no PDF extraction library available: {exc}", "text": "", "pages": 0}

    reader = PdfReader(str(path))
    chunks: List[str] = []
    page_count = len(reader.pages)
    for page in reader.pages[:max_pages]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            chunks.append("")
    return {"text": "\n".join(chunks).strip(), "pages": page_count}


def default_pdf_provider(params: Dict[str, Any]) -> Dict[str, Any]:
    max_pages = int(params.get("maxPages") or 8)
    max_chars = int(params.get("maxChars") or 12000)
    documents = []
    for path in _iter_input_paths(params, "pdf", "pdfs"):
        if not path.exists():
            documents.append({"path": str(path), "exists": False, "error": "file not found"})
            continue
        info = _file_info(path)
        extracted = _extract_pdf_text_with_library(path, max_pages)
        text = str(extracted.get("text") or "")
        info.update(
            {
                "pages": extracted.get("pages"),
                "textChars": len(text),
                "textExcerpt": text[:max_chars],
            }
        )
        if extracted.get("error"):
            info["warning"] = extracted["error"]
        documents.append(info)
    return {
        "status": "ok",
        "provider": "local_pdf_text_extractor",
        "prompt": params.get("prompt"),
        "documents": documents,
    }


def default_image_generate_provider(params: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(params.get("prompt") or "Generated image")
    filename = str(params.get("filename") or f"image_{_timestamp_id()}.svg")
    if not filename.lower().endswith(".svg"):
        filename = f"{Path(filename).stem}.svg"
    out_path = _artifact_dir("image_generate") / filename
    safe_prompt = html.escape(prompt)
    out_path.write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024">
  <rect width="1024" height="1024" fill="#eef4ff"/>
  <rect x="96" y="180" width="832" height="520" rx="32" fill="#ffffff" stroke="#2f5597" stroke-width="8"/>
  <text x="512" y="280" text-anchor="middle" font-size="44" font-family="Arial" fill="#1f2937">Generated Diagram</text>
  <text x="512" y="390" text-anchor="middle" font-size="30" font-family="Arial" fill="#374151">{safe_prompt[:160]}</text>
  <circle cx="260" cy="590" r="58" fill="#bfdbfe"/>
  <circle cx="512" cy="590" r="58" fill="#bbf7d0"/>
  <circle cx="764" cy="590" r="58" fill="#fde68a"/>
  <path d="M318 590 H454 M570 590 H706" stroke="#374151" stroke-width="10"/>
</svg>""",
        encoding="utf-8",
    )
    return {"status": "ok", "provider": "local_svg_generator", "artifact": str(out_path), "prompt": prompt}


def _write_tone_wav(path: Path, duration_seconds: float = 1.2, frequency: float = 440.0) -> None:
    sample_rate = 16000
    total = int(sample_rate * duration_seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for i in range(total):
            value = int(12000 * math.sin(2 * math.pi * frequency * i / sample_rate))
            frames.extend(struct.pack("<h", value))
        wav.writeframes(bytes(frames))


def _try_windows_tts(text: str, out_path: Path) -> bool:
    if sys.platform != "win32":
        return False
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile({json.dumps(str(out_path))}); "
        f"$s.Speak({json.dumps(text)}); "
        "$s.Dispose()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception:
        return False


def default_tts_provider(params: Dict[str, Any]) -> Dict[str, Any]:
    text = str(params.get("text") or "").strip()
    out_path = _artifact_dir("tts") / f"tts_{_timestamp_id()}.wav"
    provider = "windows_system_speech"
    if not _try_windows_tts(text, out_path):
        provider = "local_tone_fallback"
        _write_tone_wav(out_path)
    return {"status": "ok", "provider": provider, "artifact": str(out_path), "text": text}


def default_music_generate_provider(params: Dict[str, Any]) -> Dict[str, Any]:
    out_path = _artifact_dir("music_generate") / f"music_{_timestamp_id()}.wav"
    duration = float(params.get("durationSeconds") or 5)
    _write_tone_wav(out_path, duration_seconds=max(0.5, min(duration, 30.0)), frequency=523.25)
    return {"status": "ok", "provider": "local_tone_music_generator", "artifact": str(out_path), "params": params}


def default_video_generate_provider(params: Dict[str, Any]) -> Dict[str, Any]:
    out_path = _artifact_dir("video_generate") / f"video_plan_{_timestamp_id()}.json"
    storyboard = {
        "status": "ok",
        "provider": "local_video_storyboard_generator",
        "prompt": params.get("prompt"),
        "durationSeconds": params.get("durationSeconds"),
        "audioReference": params.get("audioReference"),
        "scenes": [
            {"time": "0-2s", "visual": "opening establishing shot based on prompt"},
            {"time": "2-4s", "visual": "main subject and key risk controls"},
            {"time": "4-end", "visual": "summary frame with call to action"},
        ],
    }
    out_path.write_text(json.dumps(storyboard, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**storyboard, "artifact": str(out_path)}


def default_provider_map() -> Dict[str, Any]:
    return {
        "web_search": default_web_search_provider,
        "image": default_image_provider,
        "pdf": default_pdf_provider,
        "image_generate": default_image_generate_provider,
        "music_generate": default_music_generate_provider,
        "video_generate": default_video_generate_provider,
        "tts": default_tts_provider,
    }


__all__ = [
    "default_provider_map",
    "default_web_search_provider",
    "default_image_provider",
    "default_pdf_provider",
    "default_image_generate_provider",
    "default_music_generate_provider",
    "default_video_generate_provider",
    "default_tts_provider",
]
