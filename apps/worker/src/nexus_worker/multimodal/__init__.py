"""Multimodal media processing for WhatsApp inbound."""

from nexus_worker.multimodal.processor import (
    MediaProcessor,
    MediaProcessorError,
    ProcessedMedia,
    get_media_processor,
    set_media_processor,
)

__all__ = [
    "MediaProcessor",
    "MediaProcessorError",
    "ProcessedMedia",
    "get_media_processor",
    "set_media_processor",
]
