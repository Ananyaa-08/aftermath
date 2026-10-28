def utf16_offset(canonical_text: str, code_point_offset: int) -> int:
    if not 0 <= code_point_offset <= len(canonical_text):
        raise ValueError("offset outside canonical text")
    return len(canonical_text[:code_point_offset].encode("utf-16-le")) // 2


def code_point_offset(canonical_text: str, utf16: int) -> int:
    if utf16 < 0:
        raise ValueError("negative offset")
    units = 0
    for index, char in enumerate(canonical_text):
        if units == utf16:
            return index
        units += 2 if ord(char) > 0xFFFF else 1
        if units > utf16:
            raise ValueError("offset splits a surrogate pair")
    if units == utf16:
        return len(canonical_text)
    raise ValueError("offset outside canonical text")
