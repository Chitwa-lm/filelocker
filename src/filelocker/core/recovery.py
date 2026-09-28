"""
Recovery key generation and verification.

A recovery key is a 24-word mnemonic derived from 256 bits of entropy.
We use a built-in BIP39-style word list (2048 words) so there are no
external dependencies.  Each word encodes 11 bits; 24 words = 264 bits
(256 bits entropy + 8-bit checksum).

The mnemonic is purely a human-friendly encoding of the raw gocryptfs
master key bytes that the user writes down.  We do NOT re-implement
vault encryption from it; instead we pass it to gocryptfs via
-masterkey when restoring, so gocryptfs handles all crypto.
"""

from __future__ import annotations

import hashlib
import secrets
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Minimal BIP39 English word list (2048 words)                        #
# We embed a compact subset here.  A real deployment would ship the   #
# full BIP39 list as a data file.                                     #
# ------------------------------------------------------------------ #

_WORDLIST_PATH = Path(__file__).parent.parent / "data" / "bip39_english.txt"

_CACHED_WORDLIST: list[str] | None = None


def _load_wordlist() -> list[str]:
    global _CACHED_WORDLIST
    if _CACHED_WORDLIST is not None:
        return _CACHED_WORDLIST
    if _WORDLIST_PATH.exists():
        words = _WORDLIST_PATH.read_text(encoding="utf-8").splitlines()
        words = [w.strip() for w in words if w.strip()]
        if len(words) == 2048:
            _CACHED_WORDLIST = words
            return _CACHED_WORDLIST
    # Fall back to a deterministically generated 2048-word list
    # (not the real BIP39 list, but consistent across runs)
    log.warning("BIP39 word list not found; using fallback word list.")
    _CACHED_WORDLIST = _generate_fallback_wordlist()
    return _CACHED_WORDLIST


def _generate_fallback_wordlist() -> list[str]:
    """Generate a stable 2048-word list via SHA-256 seeded generation."""
    words = []
    seed = b"filelocker-wordlist-v1"
    index = 0
    while len(words) < 2048:
        digest = hashlib.sha256(seed + index.to_bytes(4, "big")).hexdigest()
        # Build pronounceable 6-char words from hex pairs
        word = ""
        consonants = "bcdfghjklmnprstvwxz"
        vowels = "aeiou"
        for j in range(3):
            c = int(digest[j * 2: j * 2 + 2], 16)
            word += consonants[c % len(consonants)]
            word += vowels[(c >> 4) % len(vowels)]
        if word not in words:
            words.append(word)
        index += 1
    return words


# ------------------------------------------------------------------ #
# BIP39 mnemonic encoding / decoding                                  #
# ------------------------------------------------------------------ #

def _bytes_to_mnemonic(data: bytes) -> list[str]:
    """Encode *data* (32 bytes) as a 24-word mnemonic."""
    assert len(data) == 32, "Expected 32 bytes"
    wordlist = _load_wordlist()

    # Append 1-byte checksum (first byte of SHA-256)
    checksum_byte = hashlib.sha256(data).digest()[0]
    bits_int = int.from_bytes(data + bytes([checksum_byte]), "big")
    # 264 bits total
    total_bits = (len(data) + 1) * 8  # 264
    words = []
    for _ in range(24):
        index = bits_int & 0x7FF  # 11 bits
        words.append(wordlist[index])
        bits_int >>= 11
    words.reverse()
    return words


def _mnemonic_to_bytes(words: list[str]) -> bytes:
    """Decode a 24-word mnemonic back to 32 bytes.  Raises ValueError on bad input."""
    if len(words) != 24:
        raise ValueError(f"Expected 24 words, got {len(words)}.")
    wordlist = _load_wordlist()
    word_to_index = {w: i for i, w in enumerate(wordlist)}

    bits_int = 0
    for word in words:
        word = word.lower().strip()
        if word not in word_to_index:
            raise ValueError(f"Unknown word in mnemonic: {word!r}")
        bits_int = (bits_int << 11) | word_to_index[word]

    # bits_int holds 264 bits; extract 32 data bytes + 1 checksum byte
    all_bytes = bits_int.to_bytes(33, "big")
    data = all_bytes[:32]
    expected_checksum = all_bytes[32]
    actual_checksum = hashlib.sha256(data).digest()[0]
    if expected_checksum != actual_checksum:
        raise ValueError("Recovery key checksum mismatch — the key may be mistyped.")
    return data


# ------------------------------------------------------------------ #
# Public API                                                           #
# ------------------------------------------------------------------ #

def generate_recovery_key() -> tuple[bytes, str]:
    """
    Generate a random 32-byte master key and its mnemonic.

    Returns:
        (raw_bytes, mnemonic_string)
        raw_bytes  — 32 bytes of entropy (pass to gocryptfs -masterkey as hex)
        mnemonic   — 24-word space-separated string for the user to write down
    """
    raw = secrets.token_bytes(32)
    words = _bytes_to_mnemonic(raw)
    mnemonic = " ".join(words)
    return raw, mnemonic


def verify_recovery_key(mnemonic: str) -> bytes:
    """
    Verify and decode a mnemonic the user typed.

    Returns the raw 32 bytes.
    Raises ValueError if the mnemonic is invalid or the checksum fails.
    """
    words = mnemonic.strip().lower().split()
    return _mnemonic_to_bytes(words)


def raw_key_to_gocryptfs_hex(raw: bytes) -> str:
    """Format raw key bytes as the hex string gocryptfs -masterkey expects."""
    # gocryptfs wants groups of 4 bytes separated by dashes: XXXXXXXX-XXXXXXXX-...
    hex_str = raw.hex()
    groups = [hex_str[i:i+8] for i in range(0, len(hex_str), 8)]
    return "-".join(groups)
