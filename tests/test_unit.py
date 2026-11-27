#!/usr/bin/env python3
"""Unit tests for single helper functions  etc."""

import pytest
from py3createtorrent import KIB, calculate_piece_length


def test_calculate_piece_length():
    with pytest.raises(ValueError, match="Size must be"):
        calculate_piece_length(0)

    assert calculate_piece_length(1) == 16 * KIB, "should return at least 16 KiB"

    calculate_piece_length(2**20)
