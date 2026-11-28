#!/usr/bin/env python3
"""Unit tests for isolated helper functions."""

from __future__ import annotations

import hashlib

import pytest

from py3createtorrent import (
    KIB,
    MIB,
    calculate_piece_length,
    is_power_of_two,
    merkle_root,
    parse_nodes,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-1, False),
        (0, False),
        (1, True),
        (2, True),
        (3, False),
        (16 * KIB, True),
        (17 * KIB, False),
    ],
)
def test_is_power_of_two(value: int, expected: bool) -> None:
    assert is_power_of_two(value) is expected


def test_calculate_piece_length_invalid() -> None:
    with pytest.raises(ValueError, match="Size must be"):
        calculate_piece_length(0)


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (1, 16 * KIB),
        (16 * KIB - 1, 16 * KIB),
        (16 * KIB, 16 * KIB),
        (10 * MIB, 256 * KIB),
        (1000 * 1024 * MIB, 64 * MIB),  # Capped at 64 MiB
    ],
)
def test_calculate_piece_length_bounds(size: int, expected: int) -> None:
    result = calculate_piece_length(size)
    assert is_power_of_two(result)
    assert result == expected


def test_merkle_root_empty() -> None:
    # Depth 0 empty hash is 32 zero bytes
    assert merkle_root([]) == b"\x00" * 32


def test_merkle_root_two_leaves() -> None:
    a = hashlib.sha256(b"a").digest()
    b = hashlib.sha256(b"b").digest()
    expected = hashlib.sha256(a + b).digest()
    assert merkle_root([a, b]) == expected


def test_parse_nodes_valid() -> None:
    assert parse_nodes(["127.0.0.1,6881", " router.bittorrent.com , 6881 "], private=False) == [
        ["127.0.0.1", 6881],
        ["router.bittorrent.com", 6881],
    ]
