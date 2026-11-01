"""
SmartLog AI — web page log extraction (static content only).

Given the raw bytes of a fetched URL, turns the page into candidate log lines:

- text/plain (and other text/* that is not html/json): split into lines.
- application/json: walk the structure and collect strings from fields named
  message, msg, log, text, line, event — plus arrays of plain strings.
- text/html: scrape with BeautifulSoup (lxml parser). Elements considered:
  <pre>, <code>, <samp>, <tr> (cells joined with a space), <li>, and any
  element whose id/class contains "log". An optional CSS `selector` limits
  extraction to exactly that region. Nothing found -> visible body text split
  by line as a fallback.

`log_like_lines` then keeps only lines that look like logs: a timestamp, a
level keyword, or an HTTP status / key=value pattern. Whitespace is stripped,
empty and duplicate-adjacent lines are dropped, and the result is capped at
config.MAX_UPLOAD_LINES.

Limitation: static HTML/text/JSON only. Pages that render logs with
JavaScript are NOT supported. Only scrape sites you own or have permission
to scrape.
"""

import json
import re

from bs4 import BeautifulSoup

from config import MAX_UPLOAD_LINES

# --- line qualification ---------------------------------------------------------

# ISO ("2026-10-30T22:00:00" / "2026-10-30 22:00:00"), syslog ("Oct 30 22:00:01").
_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}"
)
_LEVEL_RE = re.compile(r"\b(INFO|WARN|WARNING|ERROR|CRITICAL|FATAL|DEBUG)\b", re.IGNORECASE)
_HTTP_KV_RE = re.compile(
    r"\b(?:status|code)\s*=\s*\d{3}\b|\bHTTP\s+\d{3}\b|\b[1-5]\d{2}\b.*\b\d{3}\b|\w+=[^\s]+"
)


def _is_log_like(line: str) -> bool:
    if _TIMESTAMP_RE.search(line):
        return True
    if _LEVEL_RE.search(line):
        return True
    return bool(_HTTP_KV_RE.search(line))


def log_like_lines(lines: list[str]) -> list[str]:
    """Strip/qualify/dedupe/cap raw candidate lines into ingest-ready log lines."""
    cleaned: list[str] = []
    previous: str | None = None
    for raw in lines:
        line = raw.strip()
        if not line or line == previous:
            continue
        previous = line
        if _is_log_like(line):
            cleaned.append(line)
            if len(cleaned) >= MAX_UPLOAD_LINES:
                break
    return cleaned


# --- extraction by content type ---------------------------------------------------

_JSON_FIELDS = {"message", "msg", "log", "text", "line", "event"}


def _collect_from_json(node, out: list[str]) -> None:
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and key.lower() in _JSON_FIELDS:
                out.append(value)
            elif isinstance(value, (dict, list)):
                _collect_from_json(value, out)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, str):
                out.append(item)
            else:
                _collect_from_json(item, out)


def _element_lines(element) -> list[str]:
    """Split one element's text into stripped lines."""
    text = element.get_text(" ", strip=True)
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _extract_from_html(html: str, selector: str | None) -> list[str]:
    soup = BeautifulSoup(html, "lxml")

    if selector:
        picked = soup.select(selector)
        if picked:
            return [line for element in picked for line in _element_lines(element)]

    candidates: list = []
    for tag in ("pre", "code", "samp", "tr", "li"):
        candidates.extend(soup.find_all(tag))
    for element in soup.find_all(True):
        element_id = (element.get("id") or "").lower()
        classes = [c.lower() for c in element.get("class", [])]
        if "log" in element_id or any("log" in c for c in classes):
            candidates.append(element)
    # Table rows benefit from cell separation; everything else reads as-is.
    lines = [line for element in candidates for line in _element_lines(element)]

    if not lines:
        body = soup.body or soup
        lines = [ln.strip() for ln in body.get_text(" ", strip=False).splitlines() if ln.strip()]
    return lines


def extract_lines(content: bytes, content_type: str, selector: str | None = None) -> list[str]:
    """Dispatch on the response's content type and return candidate lines."""
    ctype = (content_type or "").split(";")[0].strip().lower()
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — decode never blocks extraction
        text = ""

    if ctype == "application/json" or ctype.endswith("+json"):
        try:
            payload = json.loads(text)
            out: list[str] = []
            _collect_from_json(payload, out)
            return out
        except (ValueError, json.JSONDecodeError):
            return text.splitlines()

    if ctype.startswith("text/html") or ctype == "application/xhtml+xml":
        return _extract_from_html(text, selector)

    # text/plain and every other text/* we treat as a plain log listing.
    return text.splitlines()
