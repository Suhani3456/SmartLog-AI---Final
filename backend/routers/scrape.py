"""
SmartLog AI — web scrape route.

POST /api/scrape {url, selector?}: fetch a static page, extract log-like
lines with scraper.py and run the EXACT same ingest path the CSV upload
uses (services.run_ingest: classify, store, progress, WS broadcast of the
≤50 newest rows).

Error contract ({"detail": "<human message>"}):
  400 bad URL            422 no log-like lines found
  413 body too large     502 unreachable / timed out

SSRF note: localhost/127.0.0.1/private addresses MUST work for the demo, so
SCRAPE_ALLOW_PRIVATE defaults to true. Set it to false if this backend is
ever deployed on a public host.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from config import (
    SCRAPE_ALLOW_PRIVATE,
    SCRAPE_MAX_BODY_BYTES,
    SCRAPE_MAX_REDIRECTS,
    SCRAPE_TIMEOUT_S,
    SCRAPE_USER_AGENT,
    MAX_UPLOAD_LINES,
)
from db import UploadedFile, get_db, utcnow
from schemas import ScrapeRequest, UploadResponse
from scraper import extract_lines, log_like_lines
from services import run_ingest

router = APIRouter()


def _is_private_host(hostname: str) -> bool:
    """True for localhost / loopback / private networks (hostnames are resolved)."""
    name = hostname.lower().strip(".")
    if name in ("localhost",) or name.endswith(".localhost"):
        return True
    if name.startswith("127.") or name == "::1" or name.startswith("fc") or name.startswith("fd"):
        return True
    try:
        infos = socket.getaddrinfo(name, None)
    except OSError:
        return True  # unresolvable host: treat as unreachable/private-unsafe
    for _, _, _, _, sockaddr in infos:
        address = sockaddr[0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return True
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False


def _validate_url(raw: str) -> str:
    """Validate scheme + (SSRF-guarded) host; returns the cleaned URL."""
    try:
        parsed = urlparse(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="That URL is malformed.") from exc
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400, detail="That URL is invalid — it must start with http:// or https://."
        )
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="That URL has no host name.")
    if not SCRAPE_ALLOW_PRIVATE and _is_private_host(parsed.hostname):
        raise HTTPException(
            status_code=400,
            detail="This backend refuses private/loopback addresses (SCRAPE_ALLOW_PRIVATE=false).",
        )
    return raw


def _fetch(url: str) -> tuple[bytes, str]:
    """GET with the scrape policy: 15 s, ≤3 redirects, ≤5 MB, clear UA."""
    streamed = b""
    content_type = ""
    try:
        with httpx.Client(
            follow_redirects=True,
            max_redirects=SCRAPE_MAX_REDIRECTS,
            timeout=SCRAPE_TIMEOUT_S,
            headers={"User-Agent": SCRAPE_USER_AGENT},
        ) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                for chunk in response.iter_bytes():
                    streamed += chunk
                    if len(streamed) > SCRAPE_MAX_BODY_BYTES:
                        raise _TooLarge()
    except _TooLarge:
        raise HTTPException(status_code=413, detail="That page is larger than 5 MB.")
    except httpx.TooManyRedirects as exc:
        raise HTTPException(status_code=502, detail="That URL redirected too many times.") from exc
    except httpx.ConnectTimeout as exc:
        raise HTTPException(status_code=502, detail="Timed out while connecting to that URL.") from exc
    except httpx.ReadTimeout as exc:
        raise HTTPException(status_code=502, detail="Timed out while reading that page.") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"That URL answered with HTTP {exc.response.status_code}."
        ) from exc
    except httpx.ConnectError as exc:
        raise HTTPException(status_code=502, detail="Couldn't reach that URL — the server didn't answer.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Couldn't fetch that URL.") from exc
    return streamed, content_type


class _TooLarge(Exception):
    pass


@router.post("/api/scrape", response_model=UploadResponse, status_code=202)
def scrape_and_classify(
    body: ScrapeRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> UploadResponse:
    """Fetch a URL, extract log-like lines and ingest them like a CSV upload."""
    url = _validate_url(body.url)
    raw_content, content_type = _fetch(url)

    candidate_lines = extract_lines(raw_content, content_type, body.selector)
    lines = log_like_lines(candidate_lines)
    if not lines:
        raise HTTPException(
            status_code=422, detail="No log-like lines were found on that page."
        )

    upload = UploadedFile(
        filename=url, total_lines=len(lines), processed=0,
        incidents_created=0, status="processing", created_at=utcnow(),
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)
    # The label is the source URL, exactly like the file upload uses the
    # filename — shared services.run_ingest keeps both paths identical.
    background.add_task(run_ingest, upload.id, lines, url)
    return UploadResponse(upload_id=upload.id, filename=url, total_lines=len(lines))
