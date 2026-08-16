"""Text extraction for the client knowledge base (CP-15, v1).

"Indexing" in v1 = turn a file or a URL into clean plain text stored in
``knowledge_documents.content_text`` and count paragraph chunks. No
embeddings, no vector store: the worker injects the indexed texts into
the system prompt (``nexus_worker.runtime.knowledge_context``) under a
character cap. Semantic retrieval (pgvector) is the documented next step;
``chunk_count`` is computed today so the UI and the future indexer agree
on what a chunk is.

Failures are reported as **codes** (``KnowledgeErrorCode``), never as free
text: the console shows a translated explanation, and no upstream error
message (which could echo the URL's HTML) reaches the partner.
"""

from __future__ import annotations

import html
import io
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Final

import httpx
import structlog

from nexus_api.db.models import KnowledgeErrorCode

log = structlog.get_logger(__name__)

MAX_UPLOAD_BYTES: Final = 10 * 1024 * 1024  # 10 MB — the console rejects bigger uploads
MAX_URL_BYTES: Final = 5 * 1024 * 1024
MAX_REDIRECTS = 5


async def assert_public_url(url: str) -> None:
    """Refuse URLs whose host resolves to a non-public address (loopback,
    RFC1918, link-local incl. the cloud metadata endpoint, ULA…). Called on
    the original URL and on every redirect hop."""
    import asyncio
    import ipaddress
    import socket

    parsed = httpx.URL(url)
    if parsed.scheme not in ("http", "https") or not parsed.host:
        raise IndexingError(KnowledgeErrorCode.FETCH_FAILED)
    host = parsed.host.strip("[]")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise IndexingError(KnowledgeErrorCode.FETCH_FAILED) from exc
    if not infos:
        raise IndexingError(KnowledgeErrorCode.FETCH_FAILED)
    for info in infos:
        addr = ipaddress.ip_address(str(info[4][0]).split("%", 1)[0])
        if not addr.is_global:
            raise IndexingError(KnowledgeErrorCode.FETCH_FAILED)


MAX_CONTENT_CHARS: Final = 400_000  # extracted text ceiling per document
CHUNK_CHARS: Final = 1_200  # what "a chunk" means in v1 (paragraph-ish blocks)
FETCH_TIMEOUT_S: Final = 15.0

TEXT_MIMES: Final = frozenset({"text/plain", "text/markdown", "text/x-markdown", "text/csv"})
HTML_MIMES: Final = frozenset({"text/html", "application/xhtml+xml"})
PDF_MIMES: Final = frozenset({"application/pdf", "application/x-pdf"})
SUPPORTED_MIMES: Final = TEXT_MIMES | HTML_MIMES | PDF_MIMES
_EXT_TO_MIME: Final = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".html": "text/html",
    ".htm": "text/html",
    ".pdf": "application/pdf",
}


class IndexingError(Exception):
    """Raised with an explainable code; the caller stores it in ``error_code``."""

    def __init__(self, code: KnowledgeErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True)
class Extracted:
    text: str
    mime: str
    size_bytes: int

    @property
    def chunk_count(self) -> int:
        return count_chunks(self.text)


def guess_mime(filename: str | None, declared: str | None) -> str:
    """Prefer the declared type when it is one we support; otherwise the
    extension; otherwise the declared value verbatim (→ unsupported)."""
    declared_base = (declared or "").split(";", 1)[0].strip().lower()
    if declared_base in SUPPORTED_MIMES:
        return declared_base
    if filename:
        lower = filename.lower()
        for ext, mime in _EXT_TO_MIME.items():
            if lower.endswith(ext):
                return mime
    return declared_base or "application/octet-stream"


def count_chunks(text: str) -> int:
    if not text:
        return 0
    return max(1, -(-len(text) // CHUNK_CHARS))


class _HTMLText(HTMLParser):
    _SKIP = frozenset({"script", "style", "noscript", "template", "svg", "head"})
    _BLOCK = frozenset(
        {
            "p",
            "div",
            "br",
            "li",
            "ul",
            "ol",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "tr",
            "section",
            "article",
            "table",
            "header",
            "footer",
            "nav",
            "blockquote",
            "pre",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title and not self.title:
            self.title = data.strip()
        if self._skip_depth:
            return
        self.parts.append(data)


def html_to_text(raw: str) -> tuple[str, str]:
    """``(text, title)`` from an HTML document."""
    parser = _HTMLText()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:  # pragma: no cover - HTMLParser is lenient; belt and braces
        return clean_text(html.unescape(re.sub(r"<[^>]+>", " ", raw))), ""
    return clean_text("".join(parser.parts)), parser.title


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise IndexingError(KnowledgeErrorCode.UNSUPPORTED_TYPE) from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        log.info("knowledge.pdf_parse_failed", error=type(exc).__name__)
        raise IndexingError(KnowledgeErrorCode.UNSUPPORTED_TYPE) from exc
    return clean_text("\n\n".join(pages))


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def extract_text(data: bytes, *, mime: str, max_bytes: int = MAX_UPLOAD_BYTES) -> Extracted:
    """Bytes → clean text. Raises :class:`IndexingError` with a code."""
    if len(data) > max_bytes:
        raise IndexingError(KnowledgeErrorCode.TOO_LARGE)
    base = mime.split(";", 1)[0].strip().lower()
    if base in PDF_MIMES:
        text = _pdf_to_text(data)
    elif base in HTML_MIMES:
        text, _title = html_to_text(_decode(data))
    elif base in TEXT_MIMES:
        text = clean_text(_decode(data))
    else:
        raise IndexingError(KnowledgeErrorCode.UNSUPPORTED_TYPE)
    if not text.strip():
        raise IndexingError(KnowledgeErrorCode.EMPTY)
    if len(text) > MAX_CONTENT_CHARS:
        text = text[:MAX_CONTENT_CHARS]
    return Extracted(text=text, mime=base, size_bytes=len(data))


@dataclass(frozen=True)
class FetchedUrl:
    extracted: Extracted
    title: str


async def fetch_url(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    max_bytes: int = MAX_URL_BYTES,
) -> FetchedUrl:
    """GET ``url`` (http/https only, redirects followed) and extract text.
    Any transport/HTTP failure → ``fetch_failed``; unsupported content
    type → ``unsupported_type``; oversized → ``too_large``."""
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        raise IndexingError(KnowledgeErrorCode.FETCH_FAILED)
    own = client is None
    # Redirects are followed BY HAND so every hop is re-validated against
    # the private-network block list (SSRF); the body is streamed and cut at
    # ``max_bytes`` instead of buffered whole.
    http = client or httpx.AsyncClient(
        follow_redirects=False,
        timeout=FETCH_TIMEOUT_S,
        headers={"User-Agent": "NexusKnowledge/1.0"},
    )
    try:
        current = url
        data = b""
        resp: httpx.Response | None = None
        try:
            for _hop in range(MAX_REDIRECTS + 1):
                await assert_public_url(current)
                async with http.stream("GET", current) as streamed:
                    if streamed.status_code in (301, 302, 303, 307, 308):
                        location = streamed.headers.get("location")
                        if not location:
                            raise IndexingError(KnowledgeErrorCode.FETCH_FAILED)
                        current = str(httpx.URL(current).join(location))
                        continue
                    if streamed.status_code >= 400:
                        raise IndexingError(KnowledgeErrorCode.FETCH_FAILED)
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in streamed.aiter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise IndexingError(KnowledgeErrorCode.TOO_LARGE)
                        chunks.append(chunk)
                    data = b"".join(chunks)
                    resp = streamed
                    break
            else:
                raise IndexingError(KnowledgeErrorCode.FETCH_FAILED)
        except httpx.HTTPError as exc:
            log.info("knowledge.fetch_failed", error=type(exc).__name__)
            raise IndexingError(KnowledgeErrorCode.FETCH_FAILED) from exc
        assert resp is not None
        url = current
        mime = guess_mime(url.split("?", 1)[0], resp.headers.get("content-type"))
        extracted = extract_text(data, mime=mime, max_bytes=max_bytes)
        title = ""
        if extracted.mime in HTML_MIMES:
            _text, title = html_to_text(_decode(data))
        return FetchedUrl(extracted=extracted, title=title[:255])
    finally:
        if own:
            await http.aclose()


__all__ = [
    "CHUNK_CHARS",
    "MAX_CONTENT_CHARS",
    "MAX_UPLOAD_BYTES",
    "MAX_URL_BYTES",
    "SUPPORTED_MIMES",
    "Extracted",
    "FetchedUrl",
    "IndexingError",
    "clean_text",
    "count_chunks",
    "extract_text",
    "fetch_url",
    "guess_mime",
    "html_to_text",
]
