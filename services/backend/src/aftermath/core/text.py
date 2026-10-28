"""canon-v1 helpers. Ingestion and evidence extraction remain deferred."""

import hashlib
import json
import unicodedata

from aftermath.core.errors import InvalidEncodingError


def canonical_text(raw: bytes) -> str:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidEncodingError(
            exc.encoding, exc.object, exc.start, exc.end, exc.reason
        ) from None
    text = decoded.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", text)


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def bytes_hash(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def exact_span(text: str, start: int, end: int, expected: str | None = None) -> str:
    if not 0 <= start <= end <= len(text):
        raise ValueError("span outside canonical text")
    value = text[start:end]
    if expected is not None and value != expected:
        raise ValueError("span does not reproduce expected text")
    return value
