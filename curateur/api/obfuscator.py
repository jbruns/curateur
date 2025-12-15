"""
Credential obfuscation utilities.

SECURITY NOTE: This module provides basic XOR obfuscation for developer credentials.
This is NOT cryptographically secure and can be reverse-engineered. It exists only
to prevent casual scanning of repositories for plaintext credentials.
"""

import base64
from typing import Union

# Project-specific key derived from software identity + static salt
# This key should be changed for each major version
_PROJECT_KEY = "curateur_screenscraper_v1_2025"


def _xor_bytes(data: bytes, key: str) -> bytes:
    """
    XOR encrypt/decrypt data with a key.

    Args:
        data: Bytes to encrypt/decrypt
        key: String key to use for XOR operation

    Returns:
        XOR'd bytes
    """
    key_bytes = key.encode("utf-8")
    return bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))


def obfuscate(plaintext: str, key: str = _PROJECT_KEY) -> bytearray:
    """
    Obfuscate a plaintext string using XOR cipher.

    Args:
        plaintext: String to obfuscate
        key: Encryption key (defaults to project key)

    Returns:
        Obfuscated data as bytearray
    """
    plaintext_bytes = plaintext.encode("utf-8")
    xor_bytes = _xor_bytes(plaintext_bytes, key)
    return bytearray(xor_bytes)


def deobfuscate(obfuscated: Union[bytearray, bytes], key: str = _PROJECT_KEY) -> str:
    """
    Deobfuscate data back to plaintext.

    Args:
        obfuscated: Obfuscated data (bytearray or bytes)
        key: Decryption key (defaults to project key)

    Returns:
        Plaintext string
    """
    xor_bytes = _xor_bytes(bytes(obfuscated), key)
    return xor_bytes.decode("utf-8")
