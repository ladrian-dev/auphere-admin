"""La detección de enlaces del alta — spec 047, T047 (requisitos 5.1 y 5.2).

Lo que la persona escribe en «Información adicional» se lee al vuelo y cada
hallazgo sale como un chip con su destino en la ficha («Irá a la ficha:»):

- una **web**, con o sin esquema (``cultorbarber.com``, ``https://…``), va a
  la web del negocio;
- un enlace de **Instagram, Facebook, TikTok, LinkedIn, YouTube, X o Threads**
  va a sus redes, con el usuario cuando el enlace lo lleva;
- un **``@usuario`` suelto** se propone como Instagram, con la opción de
  cambiar la red (``alternatives``).

**Un correo no es una web**, y la arroba de un correo no es un usuario. Un
nombre de archivo (``carta.pdf``) o un número con punto (``12.50``) tampoco.

Función pura: sin red, sin base, sin reloj. La misma función la usan la ruta
de la consola (``POST /console/clients/link-detection``), el alta y la lectura
de la web (los enlaces a redes que la propia web publica).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal
from urllib.parse import urlsplit

from nexus_api.db.models.business import NETWORKS

Kind = Literal["web", "social"]
Target = Literal["website", "links"]

#: Las redes, sin la web.
SOCIAL_NETWORKS: Final[tuple[str, ...]] = tuple(n for n in NETWORKS if n != "web")
#: Las redes que usan ``@usuario``: a las que se puede cambiar un ``@`` suelto.
HANDLE_NETWORKS: Final[tuple[str, ...]] = (
    "instagram",
    "tiktok",
    "x",
    "threads",
    "youtube",
    "facebook",
)
#: Lo que la ficha guarda como mucho (``client-spec.schema.json``, ``links``).
MAX_LINKS: Final = 20
_HANDLE_RE: Final = re.compile(r"^[A-Za-z0-9._]{1,30}$")

#: Dominio de cada red → la red. ``fb.com`` y ``twitter.com`` son alias.
_NETWORK_HOSTS: Final[dict[str, str]] = {
    "instagram.com": "instagram",
    "instagr.am": "instagram",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "tiktok.com": "tiktok",
    "linkedin.com": "linkedin",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "x.com": "x",
    "twitter.com": "x",
    "threads.net": "threads",
    "threads.com": "threads",
}
#: El enlace canónico de un perfil, por red, a partir de su usuario.
_PROFILE_URL: Final[dict[str, str]] = {
    "instagram": "https://www.instagram.com/{h}",
    "facebook": "https://www.facebook.com/{h}",
    "tiktok": "https://www.tiktok.com/@{h}",
    "youtube": "https://www.youtube.com/@{h}",
    "x": "https://x.com/{h}",
    "threads": "https://www.threads.net/@{h}",
}
#: El host canónico de cada red, para rehacer un enlace sin usuario.
_CANONICAL_HOST: Final[dict[str, str]] = {
    "instagram": "www.instagram.com",
    "facebook": "www.facebook.com",
    "tiktok": "www.tiktok.com",
    "linkedin": "www.linkedin.com",
    "youtube": "www.youtube.com",
    "x": "x.com",
    "threads": "www.threads.net",
}
#: Primeras partes de una ruta que no son un perfil (una publicación, una búsqueda…).
_NOT_A_PROFILE: Final[dict[str, frozenset[str]]] = {
    "instagram": frozenset({"p", "reel", "reels", "stories", "explore", "accounts", "tv", "s"}),
    "facebook": frozenset(
        {"profile.php", "groups", "events", "share", "sharer", "watch", "pages", "photo.php"}
    ),
    "x": frozenset({"home", "search", "intent", "i", "share", "hashtag", "explore"}),
}

#: Extensiones de archivo que nunca son un dominio de primer nivel.
_FILE_EXTENSIONS: Final = frozenset(
    {
        "jpg",
        "jpeg",
        "png",
        "gif",
        "webp",
        "svg",
        "heic",
        "pdf",
        "doc",
        "docx",
        "xls",
        "xlsx",
        "ppt",
        "pptx",
        "txt",
        "csv",
        "zip",
        "rar",
        "mp3",
        "mp4",
        "mov",
        "avi",
        "wav",
        "json",
        "xml",
        "html",
        "htm",
        "exe",
        "odt",
        "ods",
        "pages",
        "key",
    }
)

_EMAIL_RE: Final = re.compile(
    r"(?<![/\w.%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+"
)
#: Una web: con esquema o sin él, dominio con al menos un punto y un TLD de letras.
_URL_RE: Final = re.compile(
    r"(?<![\w@.\-/])"
    r"(?P<url>(?:https?://)?"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}"
    r"(?::\d{2,5})?"
    r"(?:/[^\s<>\"'«»]*)?)",
    re.IGNORECASE,
)
_LONE_HANDLE_RE: Final = re.compile(r"(?<![\w@./])@(?P<h>[A-Za-z0-9._]{1,30})(?![\w@])")
_TRAILING: Final = ".,;:!?)]}»\"'\u2019\u201d"


@dataclass(frozen=True)
class DetectedLink:
    """Un hallazgo: lo que dice el chip, adónde va y cómo se cambia."""

    network: str
    #: Lo que enseña el chip: ``cultorbarber.com`` o ``@cultorbarber``.
    value: str
    #: El enlace normalizado (``https://…``), si se sabe.
    url: str | None
    #: ``@usuario`` en las redes que lo usan, si el enlace lo lleva.
    handle: str | None = None
    #: Un ``@`` suelto propuesto como Instagram: la persona puede cambiar la red.
    guessed: bool = False

    @property
    def kind(self) -> Kind:
        return "web" if self.network == "web" else "social"

    @property
    def target(self) -> Target:
        """Su destino en la ficha: la web del negocio o sus redes."""
        return "website" if self.network == "web" else "links"

    @property
    def alternatives(self) -> tuple[str, ...]:
        """Las redes a las que se puede cambiar (solo un ``@`` adivinado)."""
        if not self.guessed:
            return ()
        return tuple(n for n in HANDLE_NETWORKS if n != self.network)

    def key(self) -> tuple[str, str]:
        ident = (self.handle or self.url or self.value).lower().rstrip("/")
        return (self.network, ident)


def clean_handle(raw: str) -> str | None:
    """``cultorbarber`` o ``@cultorbarber`` → ``@cultorbarber``; inválido → ``None``."""
    bare = raw.strip().lstrip("@")
    return f"@{bare}" if _HANDLE_RE.match(bare) else None


def social_url(network: str, handle: str) -> str | None:
    """El enlace del perfil de ``handle`` en ``network``; ``None`` si la red no
    tiene perfiles por ``@usuario`` (LinkedIn) o el usuario no es válido."""
    template = _PROFILE_URL.get(network)
    cleaned = clean_handle(handle)
    if template is None or cleaned is None:
        return None
    return template.format(h=cleaned[1:])


def _strip_trailing(token: str) -> str:
    while token and token[-1] in _TRAILING:
        # Un paréntesis que cierra uno abierto dentro del enlace es del enlace.
        if token[-1] == ")" and token.count("(") >= token.count(")"):
            break
        token = token[:-1]
    return token


def _host_key(host: str) -> str:
    host = host.lower()
    for prefix in ("www.", "m.", "web.", "mobile."):
        if host.startswith(prefix):
            return host[len(prefix) :]
    return host


def _web_link(raw: str) -> DetectedLink | None:
    with_scheme = raw if re.match(r"^https?://", raw, re.IGNORECASE) else f"https://{raw}"
    try:
        parts = urlsplit(with_scheme)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if not host or "." not in host:
        return None
    tld = host.rsplit(".", 1)[-1]
    if tld in _FILE_EXTENSIONS or not tld.isalpha():
        return None
    path = parts.path.rstrip("/")
    port = f":{parts.port}" if parts.port else ""
    url = f"{parts.scheme.lower()}://{host}{port}{path}"
    if parts.query:
        url = f"{url}?{parts.query}"
    value = f"{_host_key(host)}{port}{path}"
    return DetectedLink(network="web", value=value, url=url)


def _social_link(network: str, raw: str) -> DetectedLink:
    with_scheme = raw if re.match(r"^https?://", raw, re.IGNORECASE) else f"https://{raw}"
    parts = urlsplit(with_scheme)
    segments = [s for s in parts.path.split("/") if s]
    handle: str | None = None
    if segments:
        first = segments[0]
        if network in ("tiktok", "threads", "youtube"):
            handle = clean_handle(first) if first.startswith("@") else None
        elif network in ("instagram", "facebook", "x") and first.lower() not in (
            _NOT_A_PROFILE.get(network, frozenset())
        ):
            handle = clean_handle(first)
    if handle is not None:
        url = social_url(network, handle)
        assert url is not None  # a valid handle on a handle network always has one
        return DetectedLink(network=network, value=handle, url=url, handle=handle)
    path = "/".join(segments)
    url = f"https://{_CANONICAL_HOST[network]}" + (f"/{path}" if path else "")
    return DetectedLink(network=network, value=url.split("://", 1)[1], url=url)


def classify_url(raw: str) -> DetectedLink | None:
    """Un enlace suelto → web o red; ``None`` si no es un enlace."""
    token = _strip_trailing(raw.strip())
    if not token:
        return None
    candidate = _web_link(token)
    if candidate is None:
        return None
    host = urlsplit(candidate.url or "").hostname or ""
    network = _NETWORK_HOSTS.get(_host_key(host))
    if network is not None:
        return _social_link(network, token)
    return candidate


def _overlaps(span: tuple[int, int], taken: list[tuple[int, int]]) -> bool:
    return any(span[0] < end and start < span[1] for start, end in taken)


def detect_links(text: str) -> list[DetectedLink]:
    """Los enlaces de ``text``, en el orden en que aparecen y sin repetir.

    Un ``@`` suelto que ya aparece como usuario de un enlace a una red no se
    repite: es la misma cuenta.
    """
    if not text:
        return []
    emails = [m.span() for m in _EMAIL_RE.finditer(text)]
    found: list[tuple[int, DetectedLink]] = []
    url_spans: list[tuple[int, int]] = []
    for match in _URL_RE.finditer(text):
        span = match.span("url")
        if _overlaps(span, emails):
            continue
        link = classify_url(match.group("url"))
        if link is None:
            continue
        url_spans.append(span)
        found.append((span[0], link))
    linked_handles = {link.handle.lower() for _, link in found if link.handle is not None}
    for match in _LONE_HANDLE_RE.finditer(text):
        span = match.span()
        if _overlaps(span, emails) or _overlaps(span, url_spans):
            continue
        handle = clean_handle(match.group("h"))
        if handle is None or handle.lower() in linked_handles:
            continue
        url = social_url("instagram", handle)
        found.append(
            (
                span[0],
                DetectedLink(
                    network="instagram", value=handle, url=url, handle=handle, guessed=True
                ),
            )
        )
    found.sort(key=lambda item: item[0])

    out: list[DetectedLink] = []
    seen: set[tuple[str, str]] = set()
    for _, link in found:
        key = link.key()
        if key in seen:
            continue
        seen.add(key)
        out.append(link)
        if len(out) >= MAX_LINKS:
            break
    return out


def link_from_choice(network: str, *, url: str | None, handle: str | None) -> DetectedLink | None:
    """Un chip tal como lo dejó la persona (``{network, url?, handle?}``),
    normalizado igual que uno detectado. ``None`` si no es válido."""
    if network not in NETWORKS:
        return None
    if network == "web":
        return _web_link(url) if url else None
    cleaned = clean_handle(handle) if handle else None
    if cleaned is not None:
        built = social_url(network, cleaned)
        if built is not None:
            return DetectedLink(network=network, value=cleaned, url=built, handle=cleaned)
    if url:
        link = classify_url(url)
        if link is not None and link.network == network:
            return link
    return None


__all__ = [
    "HANDLE_NETWORKS",
    "MAX_LINKS",
    "SOCIAL_NETWORKS",
    "DetectedLink",
    "classify_url",
    "clean_handle",
    "detect_links",
    "link_from_choice",
    "social_url",
]
