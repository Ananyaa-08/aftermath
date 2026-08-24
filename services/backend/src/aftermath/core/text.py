"""canon-v1 helpers. Ingestion and evidence extraction remain deferred."""

import hashlib
import json
import unicodedata


def canonical_text(raw: bytes) -> str:
    text = raw.decode("utf-8").removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", text)


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
