#!/usr/bin/env python3
"""
End-to-end integration tests for v1, v2, and hybrid torrent creation.
Verifies Bencode/BEP-52 metadata invariants and runs offline libtorrent hash checks.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias, cast

import pytest
from bencodepy import decode as bdecode
from bencodepy import encode as bencode

try:
    import libtorrent as lt
except ImportError:
    lt = None  # type: ignore[assignment]

from py3createtorrent import ProtocolVersion, TorrentSpec, create_torrent

logger = logging.getLogger(__name__)
BencodeValue: TypeAlias = int | bytes | list["BencodeValue"] | dict[bytes, "BencodeValue"]

DUMMY_TRACKERS = [
    "http://tracker1.example.com:8080/announce",
    "http://tracker2.example.com:8080/announce",
    "udp://tracker3.example.com:6969/announce",
]


@dataclass(frozen=True, slots=True)
class TorrentCase:
    name: str
    target_rel_path: str
    protocol: ProtocolVersion
    piece_size: int = 0  # KiB (0 = automatic)


def _all_protocols(name: str, rel_path: str, piece_size: int = 0) -> list[TorrentCase]:
    return [
        TorrentCase(f"{name}_{proto.value}", rel_path, proto, piece_size)
        for proto in (ProtocolVersion.V1, ProtocolVersion.V2, ProtocolVersion.HYBRID)
    ]


TEST_CASES: list[TorrentCase] = [
    # Single-file edge cases
    *_all_protocols("single_1b", "file_1b.dat"),
    *_all_protocols("single_16k_exact_block", "file_16k_exact_block.dat", piece_size=16),
    *_all_protocols("single_16k_plus_1", "file_16k_plus_1.dat", piece_size=16),
    *_all_protocols("single_32k_exact_piece", "file_32k_exact_piece.dat", piece_size=32),
    *_all_protocols("single_64k_plus_1", "file_64k_plus_1.dat", piece_size=32),
    *_all_protocols("single_4m_exact_read_chunk", "file_4m_exact_read_chunk.dat"),
    *_all_protocols("single_4m_plus_1", "file_4m_plus_1.dat"),
    # Multi-file edge cases (aligned, unaligned, empty files at start/middle/end)
    *_all_protocols("multi_edge_auto", "folder_edge_cases"),
    *_all_protocols("multi_edge_16k", "folder_edge_cases", piece_size=16),
    *_all_protocols("multi_edge_32k", "folder_edge_cases", piece_size=32),
    # Nested subfolders with empty files
    *_all_protocols("multi_nested_16k", "folder_nested", piece_size=16),
    # Multi-file folder exceeding 16 MiB slice boundary (tests parallel slicing & file seeks)
    *_all_protocols("multi_slice_17m", "folder_multi_slice"),
]


def _verify_file_tree(
    node: dict[bytes, BencodeValue],
    piece_length: int,
    piece_layers: dict[bytes, BencodeValue],
) -> None:
    """Recursively verify BEP-52 file tree entries and empty-file invariants."""
    for name, child in node.items():
        assert isinstance(name, bytes), "File tree keys must be bytes"
        assert isinstance(child, dict), "File tree nodes must be dicts"

        if name == b"":
            length = child.get(b"length")
            assert isinstance(length, int) and length >= 0, f"Invalid file length: {length!r}"

            if length == 0:
                assert b"pieces root" not in child, (
                    "BEP-52 violation: 0-byte file must NOT have a 'pieces root' in file tree"
                )
            else:
                pieces_root = child.get(b"pieces root")
                assert isinstance(pieces_root, bytes) and len(pieces_root) == 32, (
                    f"Non-empty file (length={length}) must have a 32-byte 'pieces root'"
                )
                if length > piece_length:
                    assert pieces_root in piece_layers, (
                        f"File larger than piece_length ({length} > {piece_length}) missing from 'piece layers'"
                    )
                else:
                    assert pieces_root not in piece_layers, (
                        f"Single-piece file ({length} <= {piece_length}) must NOT appear in 'piece layers'"
                    )
        else:
            _verify_file_tree(child, piece_length, piece_layers)


def verify_bencode_invariants(torrent_path: Path, protocol: ProtocolVersion, is_single_file: bool) -> None:
    """Verify structural and cryptographic invariants according to BEP 3 and BEP 52."""
    raw_bytes = torrent_path.read_bytes()
    decoded = cast(BencodeValue, bdecode(raw_bytes))
    assert isinstance(decoded, dict), "Top-level torrent structure must be a dict"
    meta: dict[bytes, BencodeValue] = decoded

    assert b"announce" in meta, "Missing 'announce' key"
    announce_list = meta.get(b"announce-list")
    assert isinstance(announce_list, list) and len(announce_list) == len(DUMMY_TRACKERS)

    raw_info = meta[b"info"]
    assert isinstance(raw_info, dict), "'info' must be a dict"
    info: dict[bytes, BencodeValue] = raw_info
    info_bencoded: bytes = bencode(info)  # type: ignore[no-untyped-call]

    piece_length = info.get(b"piece length")
    assert isinstance(piece_length, int) and piece_length > 0, "Invalid 'piece length'"

    if protocol in (ProtocolVersion.V1, ProtocolVersion.HYBRID):
        logger.debug("v1 infohash: %s", hashlib.sha1(info_bencoded).hexdigest())
        pieces = info.get(b"pieces")
        assert isinstance(pieces, bytes) and len(pieces) % 20 == 0

        if is_single_file:
            assert b"length" in info and b"files" not in info
        else:
            files = info.get(b"files")
            assert isinstance(files, list) and b"length" not in info
            if protocol == ProtocolVersion.HYBRID:
                # Find index of last non-empty real file (no pad file allowed after it)
                last_non_empty_idx = max(
                    (
                        i
                        for i, f in enumerate(files)
                        if isinstance(f, dict) and f.get(b"attr") != b"p" and cast(int, f.get(b"length", 0)) > 0
                    ),
                    default=-1,
                )

                for idx, entry in enumerate(files):
                    assert isinstance(entry, dict)
                    file_len = entry.get(b"length")
                    assert isinstance(file_len, int) and file_len >= 0
                    is_pad = entry.get(b"attr") == b"p"

                    if is_pad:
                        assert 0 < file_len < piece_length
                        assert idx < last_non_empty_idx, "No pad file should appear after the last non-empty file"
                    elif idx < last_non_empty_idx:
                        next_entry = files[idx + 1]
                        assert isinstance(next_entry, dict)
                        next_is_pad = next_entry.get(b"attr") == b"p"
                        remainder = file_len % piece_length

                        if remainder == 0:
                            assert not next_is_pad, f"Aligned/empty file (length={file_len}) must not be padded"
                        else:
                            expected_pad = piece_length - remainder
                            assert next_is_pad, f"Unaligned file (length={file_len}) must be followed by .pad"
                            assert next_entry.get(b"length") == expected_pad
    else:
        assert b"pieces" not in info
        assert b"files" not in info

    if protocol in (ProtocolVersion.V2, ProtocolVersion.HYBRID):
        logger.debug("v2 infohash: %s", hashlib.sha256(info_bencoded).hexdigest())
        assert info.get(b"meta version") == 2
        file_tree = info.get(b"file tree")
        piece_layers = meta.get(b"piece layers")
        assert isinstance(file_tree, dict)
        assert isinstance(piece_layers, dict)
        _verify_file_tree(file_tree, piece_length, piece_layers)
    else:
        assert b"meta version" not in info
        assert b"file tree" not in info
        assert b"piece layers" not in meta


def verify_with_libtorrent_offline(torrent_path: Path, save_path: Path, protocol: ProtocolVersion) -> None:
    """Verify torrent metadata and local payload hashes using libtorrent in strict offline mode."""
    assert lt is not None, "libtorrent was not loaded"

    ti = lt.torrent_info(str(torrent_path))
    info_hashes = ti.info_hashes()

    if protocol == ProtocolVersion.V1:
        assert info_hashes.has_v1() and not info_hashes.has_v2()
    elif protocol == ProtocolVersion.V2:
        assert info_hashes.has_v2() and not info_hashes.has_v1()
    elif protocol == ProtocolVersion.HYBRID:
        assert info_hashes.has_v1() and info_hashes.has_v2()

    settings = {
        "listen_interfaces": "",
        "enable_dht": False,
        "enable_lsd": False,
        "enable_upnp": False,
        "enable_natpmp": False,
        "enable_outgoing_tcp": False,
        "enable_outgoing_utp": False,
        "announce_to_all_trackers": False,
        "announce_to_all_tiers": False,
    }

    ses = lt.session(settings)
    params = lt.add_torrent_params()
    params.ti = ti
    params.trackers = []
    params.save_path = str(save_path.resolve())
    params.flags &= ~lt.torrent_flags.auto_managed
    params.flags &= ~lt.torrent_flags.seed_mode
    params.flags &= ~lt.torrent_flags.paused

    handle = ses.add_torrent(params)
    handle.force_recheck()

    deadline = time.monotonic() + 30.0
    check_started = False
    while time.monotonic() < deadline:
        s = handle.status()
        if s.errc.value() != 0:
            raise AssertionError(f"libtorrent error for {torrent_path.name}: {s.errc.message()}")
        if s.state in (lt.torrent_status.checking_files, lt.torrent_status.checking_resume_data):
            check_started = True
        elif check_started or s.state == lt.torrent_status.seeding or s.progress == 1.0:
            break
        time.sleep(0.05)
    else:
        s = handle.status()
        raise TimeoutError(f"libtorrent timed out for {torrent_path.name} (progress={s.progress * 100:.2f}%)")

    handle.pause()
    s = handle.status()
    assert s.progress == 1.0, (
        f"libtorrent hash verification incomplete for {torrent_path.name}: "
        f"{s.progress * 100:.2f}% ({s.num_pieces}/{ti.num_pieces()} pieces matched)"
    )


def _case_id(case: TorrentCase) -> str:
    return f"{case.name}_ps{case.piece_size}" if case.piece_size else case.name


@pytest.mark.parametrize("case", TEST_CASES, ids=_case_id)
def test_torrent_integration(
    case: TorrentCase,
    integration_testdata: Path,
    tmp_path: Path,
    is_libtorrent_present: bool,
) -> None:
    target = integration_testdata / case.target_rel_path
    assert target.exists(), f"Missing test fixture: {target}"

    spec = TorrentSpec(
        target=target,
        trackers=DUMMY_TRACKERS,
        piece_length=case.piece_size,
        private=False,
        protocol=case.protocol,
        output=tmp_path,
    )

    torrent_path, _, _ = create_torrent(spec)

    verify_bencode_invariants(
        torrent_path=torrent_path,
        protocol=case.protocol,
        is_single_file=target.is_file(),
    )

    if is_libtorrent_present:
        verify_with_libtorrent_offline(
            torrent_path=torrent_path,
            save_path=target.parent,
            protocol=case.protocol,
        )
