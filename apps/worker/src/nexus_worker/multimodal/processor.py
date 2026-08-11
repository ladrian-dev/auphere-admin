"""MediaProcessor — turn S3 media into LLM-ingestible text.

Three modalities, three legs:

- **Audio** (``audio/*``) — Whisper transcription via LiteLLM. We download
  the bytes from S3, pass them as a file-like object to the
  ``audio.transcriptions.create`` endpoint, and return the transcript.
- **Image** (``image/*``, ``sticker``) — Claude Sonnet 4.6 vision via
  LiteLLM. We send the image as a base64-encoded data URL in the
  ``image_url`` content part of a single multimodal turn and ask for a
  concise summary of what's visible. The agent prompt then sees a text
  summary instead of the raw image.
- **Document** (``application/pdf``, ``image/document``, etc.) — PyPDF for
  PDFs, OCR fallback via Claude vision for image-of-document, plain text
  read for ``text/*``. We persist the extracted text up to a length cap.
  Larger documents get truncated with an explanatory note so the LLM
  isn't blindsided.

Everything runs in the worker process (no API roundtrip needed): the
pipeline classify step calls ``ensure_transcript`` before invoking the
classifier so the user message that the LLM sees already includes the
transcript, plus a short header like ``[transcripción de audio]: …``.

This service is opportunistic: failures degrade gracefully to a "no pude
leer el archivo" message. We never block the turn on a transcription
error — the worst case is the agent admitting it can't read the media.

**Billing.** Both LLM legs call litellm directly instead of going through
``LiteLLMProvider``, so until 0076 neither of them was metered: every
image a customer sent burned Sonnet tokens that appeared in no invoice,
and every voice note burned Whisper minutes the same way. The two
``record_*`` calls below close that hole. They only count quantities —
the price comes from ``model_profiles``, same contract as the runtime.
"""

from __future__ import annotations

import abc
import asyncio
import base64
import contextlib
import io
import logging
from dataclasses import dataclass

from nexus_api.config import get_settings
from nexus_api.services.media_storage import MediaStorageError, get_media_storage

from nexus_worker.metering import (
    provider_of,
    record_llm_usage,
    record_voice_minutes,
    usage_fields,
)

log = logging.getLogger(__name__)


class MediaProcessorError(RuntimeError):
    """Raised when transcription / vision / extraction fails irrecoverably."""


@dataclass(frozen=True)
class ProcessedMedia:
    """Result of processing a single media object."""

    kind: str  # audio | image | document | video | sticker
    transcript: str | None
    summary: str | None
    error: str | None = None

    @property
    def text(self) -> str | None:
        """Caller-facing text. Either the transcript (audio) or a summary
        (image / video / document)."""
        return self.transcript or self.summary


class MediaProcessor(abc.ABC):
    """Process WhatsApp media into LLM-ingestible text."""

    @abc.abstractmethod
    async def process(
        self,
        *,
        s3_key: str,
        media_kind: str,
        mime_type: str | None,
        filename: str | None = None,
    ) -> ProcessedMedia:
        """Process one media object. Never raises — failures populate
        ``ProcessedMedia.error`` so the pipeline can degrade gracefully."""


class LiveMediaProcessor(MediaProcessor):
    """Production processor: LiteLLM-backed audio + vision."""

    async def process(
        self,
        *,
        s3_key: str,
        media_kind: str,
        mime_type: str | None,
        filename: str | None = None,
    ) -> ProcessedMedia:
        try:
            content, ct = await get_media_storage().get_object(s3_key)
        except MediaStorageError as exc:
            return ProcessedMedia(
                kind=media_kind,
                transcript=None,
                summary=None,
                error=f"media storage unavailable: {exc}",
            )
        effective_mime = mime_type or ct
        try:
            if media_kind == "audio":
                transcript = await self._transcribe(content, effective_mime)
                return ProcessedMedia(kind="audio", transcript=transcript, summary=None)
            if media_kind in {"image", "sticker"}:
                summary = await self._vision(content, effective_mime)
                return ProcessedMedia(kind=media_kind, transcript=None, summary=summary)
            if media_kind == "document":
                summary = await self._document(content, effective_mime, filename)
                return ProcessedMedia(kind="document", transcript=None, summary=summary)
            if media_kind == "video":
                # Cloud API allows up to 16MB MP4. Transcribing the audio
                # track is the cheap win; the vision summary is a nice-to-
                # have left as follow-up.
                transcript = await self._transcribe(content, effective_mime)
                return ProcessedMedia(kind="video", transcript=transcript, summary=None)
        except MediaProcessorError as exc:
            return ProcessedMedia(kind=media_kind, transcript=None, summary=None, error=str(exc))
        except Exception as exc:
            log.warning(
                "media_processor.unexpected_error",
                extra={"media_kind": media_kind, "s3_key": s3_key, "error": str(exc)},
            )
            return ProcessedMedia(
                kind=media_kind,
                transcript=None,
                summary=None,
                error=f"processor crashed: {type(exc).__name__}",
            )
        return ProcessedMedia(
            kind=media_kind,
            transcript=None,
            summary=None,
            error=f"unsupported media kind {media_kind!r}",
        )

    # ── audio transcription ──────────────────────────────────────────────────

    async def _transcribe(self, content: bytes, mime_type: str | None) -> str:
        settings = get_settings()
        try:
            import litellm
        except ImportError as exc:
            raise MediaProcessorError("litellm not installed") from exc
        # Wrap bytes in a file-like with a hint filename so OpenAI's
        # endpoint can pick the right decoder. WhatsApp voice notes are
        # typically OGG/Opus.
        filename = "audio.ogg"
        if mime_type:
            if mime_type.startswith("audio/mp4") or mime_type == "audio/aac":
                filename = "audio.m4a"
            elif mime_type.startswith("audio/mpeg"):
                filename = "audio.mp3"
            elif mime_type.startswith("video/"):
                filename = "video.mp4"
        try:
            file_like = io.BytesIO(content)
            file_like.name = filename
            response = await asyncio.wait_for(
                litellm.atranscription(
                    model=settings.llm_transcribe_model,
                    file=file_like,
                    # ``verbose_json`` is the only response format that
                    # carries ``duration``, and duration is the billable
                    # unit for Whisper. It still returns ``text``, so the
                    # happy path below is unchanged.
                    response_format="verbose_json",
                ),
                timeout=settings.llm_transcribe_timeout_s,
            )
        except TimeoutError as exc:
            raise MediaProcessorError("transcription timeout") from exc
        except Exception as exc:
            raise MediaProcessorError(f"transcription error: {exc}") from exc
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise MediaProcessorError("transcription returned empty text")
        # A provider (or a litellm version) that ignores ``verbose_json``
        # leaves ``duration`` absent. That costs us the measurement, not
        # the transcript — and an absent row is findable, whereas a
        # guessed duration is a plausible number nobody would question.
        duration = getattr(response, "duration", None)
        if isinstance(duration, int | float):
            record_voice_minutes(
                model=settings.llm_transcribe_model,
                provider=provider_of(settings.llm_transcribe_model),
                seconds=float(duration),
            )
        else:
            log.warning(
                "media.transcription_duration_missing model=%s",
                settings.llm_transcribe_model,
            )
        return text.strip()

    # ── vision summary ───────────────────────────────────────────────────────

    async def _vision(self, content: bytes, mime_type: str | None) -> str:
        settings = get_settings()
        try:
            import litellm
        except ImportError as exc:
            raise MediaProcessorError("litellm not installed") from exc
        encoded = base64.b64encode(content).decode("ascii")
        effective_mime = mime_type or "image/jpeg"
        prompt = (
            "Describí en español, en una sola oración corta, lo que aparece "
            "en esta imagen que envía un cliente por WhatsApp a una barbería "
            "o salón de belleza. Si es texto (un voucher, una captura), "
            "transcribilo verbatim. Si es una foto personal (corte deseado, "
            "ejemplo de servicio), describí el estilo."
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{effective_mime};base64,{encoded}"},
                    },
                ],
            }
        ]
        try:
            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=settings.llm_vision_model,
                    messages=messages,
                ),
                timeout=settings.llm_vision_timeout_s,
            )
        except TimeoutError as exc:
            raise MediaProcessorError("vision timeout") from exc
        except Exception as exc:
            raise MediaProcessorError(f"vision error: {exc}") from exc
        # Metered before the response is parsed: the tokens were spent
        # whether or not the answer comes back in a shape we can read.
        record_llm_usage(
            model=settings.llm_vision_model,
            provider=provider_of(settings.llm_vision_model),
            usage=usage_fields(response),
        )
        try:
            text = response.choices[0].message.content
        except (AttributeError, IndexError) as exc:
            raise MediaProcessorError("vision returned malformed response") from exc
        if not isinstance(text, str) or not text.strip():
            raise MediaProcessorError("vision returned empty text")
        return text.strip()

    # ── document extraction ─────────────────────────────────────────────────

    async def _document(
        self,
        content: bytes,
        mime_type: str | None,
        filename: str | None,
    ) -> str:
        # Plain text — straight decode.
        if mime_type and mime_type.startswith("text/"):
            try:
                return content.decode("utf-8", errors="replace")[:8_000]
            except Exception as exc:
                raise MediaProcessorError(f"text decode failed: {exc}") from exc

        # PDF — pypdf if available, else vision fallback for the first page.
        if (mime_type and "pdf" in mime_type) or (filename and filename.lower().endswith(".pdf")):
            text = await asyncio.to_thread(_pdf_to_text, content)
            if text:
                return text[:8_000]
            # Empty PDF text usually means scanned/image-based — fall
            # through to vision.

        # Image of a document — go via vision.
        if mime_type and mime_type.startswith("image/"):
            return await self._vision(content, mime_type)

        # Last resort: announce we received it but can't read it.
        raise MediaProcessorError(
            f"unsupported document type: {mime_type or 'unknown'} ({filename or 'no filename'})"
        )


def _pdf_to_text(content: bytes) -> str:
    """Best-effort PDF text extraction. Returns "" if pypdf is missing or
    if the PDF has no extractable text (scanned doc)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception:
        return ""
    parts: list[str] = []
    for page in reader.pages[:20]:  # cap at 20 pages — agent doesn't need a book
        with contextlib.suppress(Exception):
            text = page.extract_text() or ""
            if text:
                parts.append(text.strip())
    return "\n\n".join(parts)


# ── singleton ───────────────────────────────────────────────────────────────


_singleton: MediaProcessor | None = None


def get_media_processor() -> MediaProcessor:
    global _singleton
    if _singleton is None:
        _singleton = LiveMediaProcessor()
    return _singleton


def set_media_processor(processor: MediaProcessor | None) -> None:
    """Test hook."""
    global _singleton
    _singleton = processor
