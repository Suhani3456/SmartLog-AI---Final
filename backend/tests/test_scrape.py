"""
Tests for the scrape feature: extractor routing by content type + the
/api/scrape route's error contract. All network access stays local — the
route tests spin up a tiny static HTTP server on an ephemeral port.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

import main
from scraper import extract_lines, log_like_lines

client = TestClient(main.app)


HTML_PRE = b"""
<html><body>
<pre>
2026-10-30 09:14:22 ERROR crm-app-03 db: connection timeout after 30s, req_id=a41f2c
2026-10-30 09:15:03 WARN billing-api-02 payment: transaction declined, status=503
</pre>
</body></html>
"""

HTML_TABLE = b"""
<html><body><table>
<tr><td>2026-10-30 09:14:22</td><td>ERROR</td><td>crm db timeout req_id=a41f2c</td></tr>
<tr><td>2026-10-30 09:15:03</td><td>WARN</td><td>billing declined</td></tr>
</table></body></html>
"""

JSON_BODY = b"""
{"events": [
  {"message": "2026-10-30 09:14:22 ERROR crm db timeout, status=500"},
  {"msg": "2026-10-30 09:15:03 INFO user logged in user_id=1042"}
]}
"""

TEXT_BODY = b"""
2026-10-30 09:14:22 ERROR crm-app-03 db: connection timeout after 30s
2026-10-30 09:15:03 WARN billing payment declined

2026-10-30 09:15:03 WARN billing payment declined
plain prose line that is not a log at all
"""

HTML_NOLOG = b"<html><body><h1>Coffee and pastries</h1><p>Today's menu changed.</p></body></html>"


QUALIFIED = [
    "2026-10-30 09:14:22 ERROR crm-app-03 db: connection timeout after 30s, req_id=a41f2c",
    "2026-10-30 09:15:03 WARN billing-api-02 payment: transaction declined, status=503",
]


def test_html_pre_extraction() -> None:
    lines = extract_lines(HTML_PRE, "text/html; charset=utf-8")
    assert QUALIFIED[0] in lines and QUALIFIED[1] in lines
    assert log_like_lines(lines) == QUALIFIED  # exactly the two log lines


def test_html_table_extraction() -> None:
    lines = extract_lines(HTML_TABLE, "text/html")
    # Cells are joined with a space into one line per row.
    assert any(
        "2026-10-30 09:14:22 ERROR crm db timeout req_id=a41f2c" in line for line in lines
    )
    qualified = log_like_lines(lines)
    assert len(qualified) == 2


def test_json_extraction() -> None:
    lines = extract_lines(JSON_BODY, "application/json")
    assert any("ERROR crm db timeout, status=500" in line for line in lines)
    assert len(log_like_lines(lines)) == 2


def test_plain_text_extraction() -> None:
    lines = extract_lines(TEXT_BODY, "text/plain")
    assert len(log_like_lines(lines)) == 2  # duplicate-adjacent + prose dropped


def test_unknown_lines_are_kept_with_level_hint() -> None:
    qualified = log_like_lines([
        "2026-10-30 05:46:03 INFO retry worker: import baseline step finished",
        "no rulebook knows this pattern, leaving it unlabeled for triage",
    ])
    assert qualified == ["2026-10-30 05:46:03 INFO retry worker: import baseline step finished"]


def test_bad_url_returns_400() -> None:
    res = client.post("/api/scrape", json={"url": "ftp://example.com/logs"})
    assert res.status_code == 400
    assert "http" in res.json()["detail"].lower()


def _serve(html: bytes) -> tuple[ThreadingHTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html)

        def log_message(self, *_args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/logs.html"


def test_no_log_page_returns_422() -> None:
    server, url = _serve(HTML_NOLOG)
    try:
        res = client.post("/api/scrape", json={"url": url})
        assert res.status_code == 422
        assert "No log-like lines" in res.json()["detail"]
    finally:
        server.shutdown()
        server.server_close()


def test_scrape_over_http_ingests() -> None:
    server, url = _serve(HTML_PRE)
    try:
        res = client.post("/api/scrape", json={"url": url})
        assert res.status_code == 202, res.text
        body = res.json()
        assert body["filename"] == url
        assert body["total_lines"] == 2
    finally:
        server.shutdown()
        server.server_close()


def test_demo_site_page_ingests_a_batch() -> None:
    """The shipped demo page must yield a healthy mix of classified lines."""
    with open("demo_site/index.html", "rb") as fh:
        lines = extract_lines(fh.read(), "text/html")
    qualified = log_like_lines(lines)
    assert len(qualified) >= 40
    assert any("CRITICAL" in line for line in qualified)
    assert any("hrms" in line.lower() for line in qualified)
    assert any("billing" in line.lower() for line in qualified)


def test_selector_limits_extraction() -> None:
    html = (
        b'<html><body><div class="unrelated">'
        b"<p>2026-10-30 09:00:00 INFO should-not-appear status=200</p></div>"
        b'<pre id="logs"><p>2026-10-30 09:01:00 ERROR real payload status=500</p></pre>'
        b"</body></html>"
    )
    lines = log_like_lines(extract_lines(html, "text/html", "pre#logs"))
    assert lines == ["2026-10-30 09:01:00 ERROR real payload status=500"]


@pytest.mark.parametrize("url", ["", "notaurl", "//x", "http://"])
def test_malformed_urls_return_400(url: str) -> None:
    assert client.post("/api/scrape", json={"url": url}).status_code == 400
