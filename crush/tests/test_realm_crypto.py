# SPDX-License-Identifier: Apache-2.0
"""Tests for Realm database decryption (crush.core.realm_crypto)."""
from __future__ import annotations

import hashlib
import hmac as hmac_mod
import os

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from crush.core.passwords import WrongPasswordError
from crush.core.realm_crypto import _PAGE_SIZE, decrypt_realm_file

_KEY = os.urandom(64)


def _encrypt_page(plaintext: bytes, aes_key: bytes, hmac_key: bytes, iv1: int, data_pos: int) -> tuple[bytes, bytes]:
    """Test-only inverse of _aes_cbc_decrypt_page + HMAC, to build a
    synthetic encrypted fixture without needing a real Realm-encrypted
    sample -- same construction the production decrypt logic expects."""
    iv = iv1.to_bytes(4, "little") + data_pos.to_bytes(8, "little") + b"\x00" * 4
    encryptor = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()
    hmac_val = hmac_mod.new(hmac_key, ciphertext, hashlib.sha224).digest()
    return ciphertext, hmac_val


def _encrypt_realm_file(plaintext: bytes, key: bytes) -> bytes:
    assert len(plaintext) % _PAGE_SIZE == 0
    aes_key, hmac_key = key[:32], key[32:64]
    pages = [plaintext[i : i + _PAGE_SIZE] for i in range(0, len(plaintext), _PAGE_SIZE)]

    out = bytearray()
    for block_start in range(0, len(pages), 64):
        block_pages = pages[block_start : block_start + 64]
        iv_table = bytearray()
        ciphertexts = []
        for i, page in enumerate(block_pages):
            data_pos = (block_start + i) * _PAGE_SIZE
            iv1 = block_start + i + 1  # any nonzero value
            ciphertext, hmac_val = _encrypt_page(page, aes_key, hmac_key, iv1, data_pos)
            ciphertexts.append(ciphertext)
            iv_table += iv1.to_bytes(4, "little") + hmac_val + (0).to_bytes(4, "little") + b"\x00" * 28
        iv_table += b"\x00" * (_PAGE_SIZE - len(iv_table))  # pad metadata page to full size
        out += iv_table
        for c in ciphertexts:
            out += c
    return bytes(out)


def test_decrypt_realm_file_round_trips_single_block() -> None:
    plaintext = os.urandom(_PAGE_SIZE * 3)
    encrypted = _encrypt_realm_file(plaintext, _KEY)
    assert decrypt_realm_file(encrypted, _KEY) == plaintext


def test_decrypt_realm_file_round_trips_across_block_boundary() -> None:
    # 65 pages forces a second metadata block (pages_per_block=64)
    plaintext = os.urandom(_PAGE_SIZE * 65)
    encrypted = _encrypt_realm_file(plaintext, _KEY)
    assert decrypt_realm_file(encrypted, _KEY) == plaintext


def test_decrypt_realm_file_never_written_page_reads_as_zero() -> None:
    """iv1 == 0 in the IVTable entry means the page was never written --
    a real sparse-file state, not corruption -- and must decode to plain
    zero bytes rather than raising."""
    plaintext = os.urandom(_PAGE_SIZE * 2)
    encrypted = bytearray(_encrypt_realm_file(plaintext, _KEY))
    # zero out the second page's IVTable entry (iv1 at offset 64 within the metadata page)
    encrypted[64:128] = b"\x00" * 64
    result = decrypt_realm_file(bytes(encrypted), _KEY)
    assert result[:_PAGE_SIZE] == plaintext[:_PAGE_SIZE]
    assert result[_PAGE_SIZE:] == b"\x00" * _PAGE_SIZE


def test_decrypt_realm_file_wrong_key_raises() -> None:
    plaintext = os.urandom(_PAGE_SIZE * 2)
    encrypted = _encrypt_realm_file(plaintext, _KEY)
    wrong_key = os.urandom(64)
    with pytest.raises(WrongPasswordError):
        decrypt_realm_file(encrypted, wrong_key)


def test_decrypt_realm_file_wrong_key_length_raises() -> None:
    with pytest.raises(WrongPasswordError):
        decrypt_realm_file(b"\x00" * _PAGE_SIZE * 2, b"short")
