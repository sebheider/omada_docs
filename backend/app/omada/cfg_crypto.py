"""Decryption of native Omada controller backup files (``.cfg``).

Ported from Omada_Backup_Decryptor by jgrimard
(https://github.com/jgrimard/Omada_Backup_Decryptor), MIT License, Copyright (c) 2026 jgrimard.
See THIRD_PARTY_NOTICES.md for the full license text.

File format::

    .cfg = RC4( GZIP( JSON ) )

The RC4 key is a static 256-byte array embedded in the controller whose first 8-byte block is
TEA-decrypted (64 rounds) at runtime. Because the key is static, every controller produces backups
that can be decrypted without a password.

Only decryption is implemented. This application is read-only towards the controller and therefore
never creates (re-encrypted) backup files that could be restored.
"""

from __future__ import annotations

import zlib
from functools import lru_cache

GZIP_MAGIC = b"\x1f\x8b"
MAX_DECOMPRESSED_BYTES = 128 * 1024 * 1024

_MASK = 0xFFFFFFFF
_TEA_KEY = (-707509657, -1887749506, 1427902494, -1686606610)
_DELTA = -1640531527  # 0x9E3779B9 as signed 32-bit int
_OBFUSCATED_KEY = (
    112, 122, 14, 91, -110, 101, -10, 34, 51, 59, 94, 118, 50, 108, 63, 50,
    94, 52, 94, 104, 67, 100, 117, 114, 110, 53, 47, 79, 38, 103, 43, 59,
    70, 43, 72, 119, 107, 61, 108, 82, 84, 80, 36, 95, 106, 72, 53, 101,
    105, 81, 38, 47, 65, 110, 47, 47, 99, 79, 72, 36, 50, 108, 68, 48,
    120, 89, 68, 97, 95, 70, 65, 35, 33, 84, 53, 49, 64, 102, 105, 88,
    84, 100, 76, 49, 63, 107, 82, 45, 58, 115, 126, 101, 63, 95, 45, 72,
    50, 45, 84, 36, 100, 117, 43, 110, 114, 65, 72, 98, 112, 103, 78, 45,
    121, 98, 114, 52, 117, 37, 57, 36, 40, 126, 45, 66, 64, 101, 100, 73,
    122, 108, 114, 100, 112, 110, 98, 94, 37, 102, 37, 95, 51, 89, 90, 49,
    115, 95, 103, 89, 106, 103, 101, 56, 117, 99, 106, 115, 108, 118, 89, 33,
    69, 33, 82, 107, 102, 64, 76, 117, 61, 122, 40, 45, 38, 75, 116, 87,
    99, 100, 41, 63, 73, 119, 37, 57, 43, 57, 42, 69, 61, 36, 42, 83,
    95, 58, 112, 52, 118, 47, 77, 112, 57, 115, 57, 56, 61, 51, 108, 89,
    117, 67, 100, 99, 107, 121, 36, 101, 100, 113, 70, 108, 37, 79, 55, 47,
    49, 72, 114, 73, 56, 78, 64, 85, 122, 33, 99, 37, 76, 75, 33, 108,
    110, 117, 88, 114, 115, 73, 80, 110, 47, 118, 97, 37, 114, 89, 85, 71,
)


class CfgError(ValueError):
    """Raised when a file is not a decryptable Omada ``.cfg`` backup."""


def _s32(x: int) -> int:
    """Truncate to a signed 32-bit int (Java int overflow semantics)."""
    x &= _MASK
    return x - 0x100000000 if x & 0x80000000 else x


def _tea_decrypt_block(y: int, z: int) -> tuple[int, int]:
    a, b, c, d = _TEA_KEY
    total = _s32(_DELTA * 64)
    for _ in range(64):
        z = _s32(z - _s32(_s32(_s32(y << 4) + c) ^ _s32(y + total) ^ _s32((y >> 5) + d)))
        y = _s32(y - _s32(_s32(_s32(z << 4) + a) ^ _s32(z + total) ^ _s32((z >> 5) + b)))
        total = _s32(total - _DELTA)
    return y, z


@lru_cache(maxsize=1)
def rc4_key() -> bytes:
    """The controller's RC4 key: the static array with its first 8-byte block TEA-decrypted."""
    raw = bytes(b & 0xFF for b in _OBFUSCATED_KEY)
    y, z = _tea_decrypt_block(int.from_bytes(raw[0:4], "big", signed=True),
                              int.from_bytes(raw[4:8], "big", signed=True))
    return (y & _MASK).to_bytes(4, "big") + (z & _MASK).to_bytes(4, "big") + raw[8:]


def rc4(data: bytes) -> bytes:
    """RC4 with the controller key (symmetric, so it both encrypts and decrypts).

    Pure Python because OpenSSL/cryptography only accept RC4 keys up to 256 bits; the controller key
    is 2048 bits long.
    """
    key = rc4_key()
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
    stream = bytearray(len(data))
    i = j = 0
    for k in range(len(data)):
        i = (i + 1) & 0xFF
        si = s[i]
        j = (j + si) & 0xFF
        sj = s[j]
        s[i] = sj
        s[j] = si
        stream[k] = s[(si + sj) & 0xFF]
    n = len(data)
    return (int.from_bytes(data, "big") ^ int.from_bytes(stream, "big")).to_bytes(n, "big")


def looks_like_cfg(content: bytes) -> bool:
    """True if the content decrypts to a gzip/deflate header (cheap check on the first bytes only)."""
    return len(content) >= 3 and rc4(content[:3]) == GZIP_MAGIC + b"\x08"


def decrypt_cfg(content: bytes, max_size: int = MAX_DECOMPRESSED_BYTES) -> bytes:
    """Decrypt and decompress a ``.cfg`` backup. Returns the inner (JSON) bytes.

    Decompression is bounded by ``max_size`` to protect against decompression bombs.
    """
    if len(content) < 20:
        raise CfgError("The file is too small to be an Omada controller backup.")
    stream = rc4(content)
    if stream[:2] != GZIP_MAGIC:
        raise CfgError("The file could not be decrypted – it is not an Omada controller backup (.cfg) "
                       "or uses an unknown encryption key.")
    inflater = zlib.decompressobj(wbits=31)
    out = bytearray()
    data = stream
    try:
        while data and not inflater.eof:
            out += inflater.decompress(data, max_size + 1 - len(out))
            if len(out) > max_size:
                raise CfgError(f"The decrypted backup exceeds the maximum size of {max_size // (1024 * 1024)} MB.")
            data = inflater.unconsumed_tail
    except zlib.error as exc:
        raise CfgError(f"The decrypted backup is corrupt (gzip error: {exc}).") from exc
    if not inflater.eof:
        raise CfgError("The backup file is truncated (incomplete gzip stream).")
    return bytes(out)
