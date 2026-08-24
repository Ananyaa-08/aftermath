def utf16_offset(canonical_text: str, code_point_offset: int) -> int:
    if not 0 <= code_point_offset <= len(canonical_text):
        raise ValueError("offset outside canonical text")
    return len(canonical_text[:code_point_offset].encode("utf-16-le")) // 2
