#!/usr/bin/env python3
"""
Tests v1, v2, and hybrid torrent creation against single-file and multi-file
fixtures, verifies Bencode/BEP-52 metadata invariants, and runs `libtorrent`
verification checks.
"""

from __future__ import annotations

import hashlib
import logging
import time
import warnings
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias, cast

import cachedir_tag
import pytest
from bencodepy import decode as bdecode
from bencodepy import encode as bencode

try:
    import libtorrent as lt
except ImportError:
    lt = None  # type: ignore[assignment]

from create_random_file import create_random_file
from create_random_folder import create_random_folder

from py3createtorrent import ProtocolVersion, TorrentSpec, create_torrent, main

PROJECT_ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)
BencodeValue: TypeAlias = int | bytes | list["BencodeValue"] | dict[bytes, "BencodeValue"]


@dataclass(frozen=True, slots=True)
class TorrentCase:
    name: str
    target_rel_path: str
    protocol: ProtocolVersion
    piece_size: int = 0


TEST_CASES_SINGLE_FILE = [
    TorrentCase("single_file_16k_v2", "random_file_16k.dat", ProtocolVersion.V2),
    TorrentCase("single_file_17k_v2", "random_file_17k.dat", ProtocolVersion.V2),
    TorrentCase("single_file_48k_v2", "random_file_48k.dat", ProtocolVersion.V2),
    TorrentCase("single_file_64k_v2", "random_file_64k.dat", ProtocolVersion.V2),
    TorrentCase("single_file_65k_v2", "random_file_65k.dat", ProtocolVersion.V2),
    TorrentCase("single_file_65k_v2", "random_file_65k.dat", ProtocolVersion.V2, 32),
    TorrentCase("single_file_100k_v2", "random_file_100k.dat", ProtocolVersion.V2),
    TorrentCase("single_file_100k_v2", "random_file_100k.dat", ProtocolVersion.V2, 32),
    TorrentCase("single_file_v1", "random_file_50m.dat", ProtocolVersion.V1),
    TorrentCase("single_file_v2", "random_file_50m.dat", ProtocolVersion.V2),
    TorrentCase("single_file_hybrid", "random_file_50m.dat", ProtocolVersion.HYBRID),
]

TEST_CASES_MULTI_FILE = [
    TorrentCase("multi_file_v1", "random_folder_big_files", ProtocolVersion.V1),
    TorrentCase("multi_file_v2", "random_folder_big_files", ProtocolVersion.V2),
    TorrentCase("multi_file_hybrid", "random_folder_big_files", ProtocolVersion.HYBRID),
    TorrentCase("multi_file_v1", "random_folder_tiny_files", ProtocolVersion.V1),
    TorrentCase("multi_file_v2", "random_folder_tiny_files", ProtocolVersion.V2),
    TorrentCase("multi_file_hybrid", "random_folder_tiny_files", ProtocolVersion.HYBRID),
    TorrentCase("multi_file_hybrid", "random_folder_tiny_files", ProtocolVersion.HYBRID, 16),
    TorrentCase("multi_file_hybrid", "random_folder_tiny_files", ProtocolVersion.HYBRID, 32),
    TorrentCase("multi_file_hybrid_with_empty_files", "random_folder_with_empty_files", ProtocolVersion.HYBRID),
    TorrentCase("multi_file_hybrid_with_subfolder", "random_folder_with_subfolder", ProtocolVersion.HYBRID),
    TorrentCase("multi_file_hybrid_with_subfolder", "random_folder_with_subfolder", ProtocolVersion.HYBRID, 16),
]

TEST_CASES = TEST_CASES_SINGLE_FILE + TEST_CASES_MULTI_FILE


def ensure_testdata_is_generated():
    testdata_path = PROJECT_ROOT / "tests" / "testdata"
    if testdata_path.is_dir():
        logger.info("Testdata directory already exists. Nothing to do.")
        return

    logger.info("Creating fresh set of random testdata here: %s", testdata_path)
    testdata_path.mkdir()
    cachedir_tag.tag(testdata_path)
    (testdata_path / "empty_folder").mkdir()

    seed = 0
    KIB = 2**10
    MIB = 2**20
    logger.info("  Creating random files with various sizes...")
    create_random_file(testdata_path / "random_file_50m.dat", 50 * MIB, seed)
    for kb in [16, 17, 48, 64, 65, 100]:
        create_random_file(testdata_path / f"random_file_{kb}k.dat", kb * KIB, seed)

    logger.info("  Creating random_folder_tiny_files...")
    create_random_folder(testdata_path / "random_folder_tiny_files", 200, 1, 200 * KIB, seed)
    logger.info("  Creating random_folder_big_files...")
    create_random_folder(testdata_path / "random_folder_big_files", 30, 1 * KIB, 10 * MIB, seed)
    logger.info("  Creating random_folder_with_empty_files...")
    create_random_folder(testdata_path / "random_folder_with_empty_files", 50, 1, 200 * KIB, seed)
    (testdata_path / "random_folder_with_empty_files" / "empty123.txt").touch()
    (testdata_path / "random_folder_with_empty_files" / "empty456.json").touch()
    (testdata_path / "random_folder_with_empty_files" / "empty789.yaml").touch()

    logger.info("  Creating random_folder_with_subfolder...")
    create_random_folder(testdata_path / "random_folder_with_subfolder", 20, 1, 200 * KIB, seed)
    create_random_folder(testdata_path / "random_folder_with_subfolder" / "subfolder1", 5, 1, 200 * KIB, seed)
    create_random_folder(testdata_path / "random_folder_with_subfolder" / "subfolder2", 5, 1, 200 * KIB, seed)
    create_random_folder(
        testdata_path / "random_folder_with_subfolder" / "subfolder2" / "subsubfolder1", 5, 1, 200 * KIB, seed
    )
    (testdata_path / "random_folder_with_subfolder" / "empty123.txt").touch()
    (testdata_path / "random_folder_with_subfolder" / "empty456.json").touch()
    (testdata_path / "random_folder_with_subfolder" / "empty789.yaml").touch()
    (testdata_path / "random_folder_with_subfolder" / "subfolder1" / "empty.txt").touch()


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
            # Leaf file entry
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
            # Directory node
            _verify_file_tree(child, piece_length, piece_layers)


def verify_bencode_invariants(torrent_path: Path, protocol: ProtocolVersion, is_single_file: bool) -> None:
    """
    Verify structural and cryptographic invariants of the generated .torrent file
    according to BEP 3 and BEP 52.
    """
    raw_bytes = torrent_path.read_bytes()
    decoded = cast(BencodeValue, bdecode(raw_bytes))
    assert isinstance(decoded, dict), "Top-level torrent structure must be a dict"
    meta: dict[bytes, BencodeValue] = decoded

    # Check trackers from best3
    assert b"announce" in meta, "Missing 'announce' key"
    announce_list = meta.get(b"announce-list")
    assert isinstance(announce_list, list), "Missing or invalid 'announce-list' key for best3 trackers"
    assert len(announce_list) == 3, f"Expected 3 trackers, got {len(announce_list)}"

    raw_info = meta[b"info"]
    assert isinstance(raw_info, dict), "'info' must be a dict"
    info: dict[bytes, BencodeValue] = raw_info
    info_bencoded: bytes = bencode(info)  # type: ignore[no-untyped-call]

    piece_length = info.get(b"piece length")
    assert isinstance(piece_length, int) and piece_length > 0, "Invalid 'piece length'"

    if protocol in (ProtocolVersion.V1, ProtocolVersion.HYBRID):
        v1_infohash = hashlib.sha1(info_bencoded).hexdigest()
        logger.debug("  v1 infohash: %s", v1_infohash)
        pieces = info.get(b"pieces")
        assert isinstance(pieces, bytes), "v1/hybrid torrent missing 'pieces'"
        assert len(pieces) % 20 == 0, "v1 'pieces' length must be a multiple of 20"

        if is_single_file:
            assert b"length" in info and b"files" not in info
        else:
            files = info.get(b"files")
            assert isinstance(files, list) and b"length" not in info
            if protocol == ProtocolVersion.HYBRID:
                pad_entries = [
                    f
                    for f in files
                    if isinstance(f, dict)
                    and f.get(b"attr") == b"p"
                    and isinstance(path_list := f.get(b"path"), list)
                    and path_list[0] == b".pad"
                ]
                logger.debug("  Hybrid BEP-47 pad files count: %d", len(pad_entries))

                # Verify padding alignment and empty-file rules in v1 'files' list
                for idx, entry in enumerate(files):
                    assert isinstance(entry, dict)
                    file_len = entry.get(b"length")
                    assert isinstance(file_len, int) and file_len >= 0
                    is_pad = entry.get(b"attr") == b"p"

                    if is_pad:
                        assert 0 < file_len < piece_length, (
                            f"Invalid pad file length {file_len} (must be 0 < len < {piece_length})"
                        )
                    elif idx < len(files) - 1:
                        next_entry = files[idx + 1]
                        assert isinstance(next_entry, dict)
                        next_is_pad = next_entry.get(b"attr") == b"p"
                        remainder = file_len % piece_length

                        if remainder == 0:
                            # Covers both 0-byte files and exact piece-multiple files
                            assert not next_is_pad, (
                                f"File of length {file_len} is already aligned to piece_length "
                                f"{piece_length} and must NOT be followed by a .pad file"
                            )
                        else:
                            expected_pad = piece_length - remainder
                            assert next_is_pad, (
                                f"Unaligned file (length={file_len}) in hybrid torrent must be followed by a .pad file"
                            )
                            assert next_entry.get(b"length") == expected_pad, (
                                f"Expected pad length {expected_pad}, got {next_entry.get(b'length')!r}"
                            )
    else:
        assert b"pieces" not in info, "Pure v2 torrent must not contain v1 'pieces'"
        assert b"files" not in info, "Pure v2 torrent must not contain v1 'files'"

    if protocol in (ProtocolVersion.V2, ProtocolVersion.HYBRID):
        v2_infohash = hashlib.sha256(info_bencoded).hexdigest()
        logger.debug("  v2 infohash: %s", v2_infohash)
        assert info.get(b"meta version") == 2, "v2/hybrid torrent must have 'meta version' == 2"

        file_tree = info.get(b"file tree")
        assert isinstance(file_tree, dict), "v2/hybrid torrent missing 'file tree'"

        piece_layers = meta.get(b"piece layers")
        assert isinstance(piece_layers, dict), "v2/hybrid torrent missing 'piece layers'"

        _verify_file_tree(file_tree, piece_length, piece_layers)
    else:
        assert b"meta version" not in info, "Pure v1 torrent must not contain 'meta version'"
        assert b"file tree" not in info, "Pure v1 torrent must not contain 'file tree'"
        assert b"piece layers" not in meta, "Pure v1 torrent must not contain 'piece layers'"


def verify_with_libtorrent_offline(
    torrent_path: Path,
    save_path: Path,
    protocol: ProtocolVersion,
) -> None:
    """
    Verify torrent metadata and local payload hashes using libtorrent in strict
    offline mode (no listening sockets, no DHT/LSD/UPnP, no tracker announces).
    """
    assert lt is not None, "libtorrent was not loaded"

    ti = lt.torrent_info(str(torrent_path))
    info_hashes = ti.info_hashes()

    if protocol == ProtocolVersion.V1:
        assert info_hashes.has_v1() and not info_hashes.has_v2(), "libtorrent did not parse torrent as pure v1"
    elif protocol == ProtocolVersion.V2:
        assert info_hashes.has_v2() and not info_hashes.has_v1(), "libtorrent did not parse torrent as pure v2"
    elif protocol == ProtocolVersion.HYBRID:
        assert info_hashes.has_v1() and info_hashes.has_v2(), "libtorrent did not parse torrent as v1+v2 hybrid"

    settings = {
        "listen_interfaces": "",  # Opens no listening sockets (prevents Windows Firewall prompt)
        "enable_dht": False,  # Disables Distributed Hash Table
        "enable_lsd": False,  # Disables Local Service Discovery (multicast)
        "enable_upnp": False,  # Disables UPnP port mapping
        "enable_natpmp": False,  # Disables NAT-PMP port mapping
        "enable_outgoing_tcp": False,  # Blocks all outgoing TCP peer/tracker connections
        "enable_outgoing_utp": False,  # Blocks all outgoing uTP peer/tracker connections
        "announce_to_all_trackers": False,
        "announce_to_all_tiers": False,
    }

    ses = lt.session(settings)

    params = lt.add_torrent_params()
    params.ti = ti
    params.trackers = []  # Strip trackers from ti so no announces are ever queued
    params.save_path = str(save_path.resolve())
    # Allow libtorrent to run the file check immediately, but disable auto_managed and seed_mode
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
            raise AssertionError(f"libtorrent verification error for {torrent_path.name}: {s.errc.message()}")
        if s.state in (
            lt.torrent_status.checking_files,
            lt.torrent_status.checking_resume_data,
        ):
            check_started = True
        elif check_started or s.state == lt.torrent_status.seeding or s.progress == 1.0:
            break
        time.sleep(0.05)
    else:
        s = handle.status()
        raise TimeoutError(
            f"libtorrent verification timed out for {torrent_path.name} "
            f"(state={s.state}, progress={s.progress * 100:.2f}%)"
        )

    handle.pause()
    s = handle.status()
    logger.debug(
        "  libtorrent offline verification: %.2f%% (%d/%d pieces)",
        s.progress * 100,
        s.num_pieces,
        ti.num_pieces(),
    )
    assert s.progress == 1.0, (
        f"libtorrent hash verification incomplete for {torrent_path.name}: "
        f"{s.progress * 100:.2f}% ({s.num_pieces}/{ti.num_pieces()} pieces matched)"
    )


@pytest.fixture(scope="session")
def testdata_dir() -> Path:
    """Generate random test fixtures once per test session."""
    ensure_testdata_is_generated()
    return PROJECT_ROOT / "tests" / "testdata"


@pytest.fixture(scope="session")
def is_libtorrent_present():
    if lt is None:
        warnings.warn(
            "libtorrent is not installed; skipping libtorrent offline verification.",
            UserWarning,
            stacklevel=2,
        )
        return False
    else:
        return True


def _case_id(case: TorrentCase) -> str:
    # Generate a unique, readable test ID for pytest output
    if case.piece_size:
        return f"{case.name}_ps{case.piece_size}"
    return case.name


@pytest.mark.parametrize("case", TEST_CASES, ids=_case_id)
def test_create_torrent(case: TorrentCase, testdata_dir: Path, tmp_path: Path, is_libtorrent_present: bool) -> None:
    target = testdata_dir / case.target_rel_path
    assert target.exists(), f"Missing test fixture: {target}"

    spec = TorrentSpec(
        target=target,
        trackers=["best3"],
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
        assert lt is not None, "lt (libtorrent) should not be None"
        verify_with_libtorrent_offline(
            torrent_path=torrent_path,
            save_path=target.parent,
            protocol=case.protocol,
        )


def test_cli(testdata_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = testdata_dir / TEST_CASES_SINGLE_FILE[0].target_rel_path

    main([str(target), "--output", str(tmp_path)])
    captured = capsys.readouterr()

    expected_outputs = [
        "Name",
        "Protocol",
        "Size",
        "Pieces",
        "Comment",
        "Private",
        "Creation date",
        "DHT bootstrap nodes",
        "Webseeds",
        "Primary tracker",
        "Backup trackers",
    ]
    for expected_output in expected_outputs:
        assert expected_output in captured.out, f"cli stdout is missing expected output '{expected_output}'"


def test_comment(testdata_dir: Path, tmp_path: Path):
    target = testdata_dir / TEST_CASES_SINGLE_FILE[0].target_rel_path
    spec = TorrentSpec(target=target, output=tmp_path, comment="my_comment")
    _, metainfo, _ = create_torrent(spec)
    assert "comment" in metainfo, "metainfo['comment'] does not exist"
    assert metainfo["comment"] == "my_comment", "metainfo['comment'] does not have expected value"


def test_date(testdata_dir: Path, tmp_path: Path):
    target = testdata_dir / TEST_CASES_SINGLE_FILE[0].target_rel_path
    spec = TorrentSpec(target=target, output=tmp_path, date=1337)
    _, metainfo, _ = create_torrent(spec)
    assert "creation date" in metainfo, "metainfo['creation date'] does not exist"
    assert metainfo["creation date"] == 1337, "metainfo['creation date'] does not have expected value"


def test_date_disabled(testdata_dir: Path, tmp_path: Path):
    target = testdata_dir / TEST_CASES_SINGLE_FILE[0].target_rel_path
    spec = TorrentSpec(target=target, output=tmp_path, date=-2)
    _, metainfo, _ = create_torrent(spec)
    assert "creation date" not in metainfo, "metainfo['creation date'] should not exist"


def test_date_invalid(testdata_dir: Path, tmp_path: Path):
    target = testdata_dir / TEST_CASES_SINGLE_FILE[0].target_rel_path

    spec = TorrentSpec(target=target, output=tmp_path, date=-3)
    with pytest.raises(ValueError, match="Invalid date"):
        create_torrent(spec)

    spec = TorrentSpec(target=target, output=tmp_path, date=-2)
    _, metainfo, _ = create_torrent(spec)
    assert "creation date" not in metainfo, "metainfo['creation date'] should not exist"


def test_node(testdata_dir: Path, tmp_path: Path):
    target = testdata_dir / TEST_CASES_SINGLE_FILE[0].target_rel_path
    spec = TorrentSpec(target=target, output=tmp_path, nodes=["host,1337"])
    _, metainfo, _ = create_torrent(spec)
    assert "nodes" in metainfo, "metainfo['nodes'] does not exist"
    assert isinstance(metainfo["nodes"], list), "metainfo['nodes'] is not a list"
    assert metainfo["nodes"][0] == ["host", 1337], "metainfo['nodes'] does not contain the correct node"


@pytest.mark.parametrize(
    ("private", "nodes", "expectation"),
    [
        pytest.param(
            True,
            ["host,123"],
            pytest.raises(ValueError, match="private torrent"),
            id="private_with_nodes",
        ),
        pytest.param(
            False,
            ["invalid_node_spec"],
            pytest.raises(ValueError, match="Invalid format"),
            id="invalid_format",
        ),
        pytest.param(
            False,
            ["host,non_numeric_port"],
            pytest.raises(ValueError, match="Invalid port number"),
            id="non_numeric_port",
        ),
        pytest.param(
            False,
            ["host,0"],
            pytest.raises(ValueError, match="Port number out of range"),
            id="port_too_low",
        ),
        pytest.param(
            False,
            ["host,65536"],
            pytest.raises(ValueError, match="Port number out of range"),
            id="port_too_high",
        ),
    ],
)
def test_nodes_that_are_invalid(
    testdata_dir: Path,
    tmp_path: Path,
    private: bool,
    nodes: list[str],
    expectation: AbstractContextManager[Any],
) -> None:
    target = testdata_dir / TEST_CASES_SINGLE_FILE[0].target_rel_path
    spec = TorrentSpec(target=target, private=private, nodes=nodes, output=tmp_path)

    with expectation:
        create_torrent(spec)


def test_piece_length_invalid(testdata_dir: Path, tmp_path: Path):
    target = testdata_dir / TEST_CASES_SINGLE_FILE[0].target_rel_path

    # Less than 16 KiB
    spec = TorrentSpec(target=target, output=tmp_path, piece_length=15)
    with pytest.raises(ValueError, match="Piece length"):
        create_torrent(spec)

    # Not a power of 2
    spec = TorrentSpec(target=target, output=tmp_path, piece_length=17)
    with pytest.raises(ValueError, match="Piece length"):
        create_torrent(spec)


def test_private(testdata_dir: Path, tmp_path: Path):
    target = testdata_dir / TEST_CASES_SINGLE_FILE[0].target_rel_path
    spec = TorrentSpec(target=target, output=tmp_path, private=True)
    _, metainfo, _ = create_torrent(spec)
    assert "private" in metainfo["info"], "metainfo['info'] does not have 'private'"
    assert metainfo["info"]["private"] == 1, "metainfo['info']['private'] is not 1"


def test_source(testdata_dir: Path, tmp_path: Path):
    target = testdata_dir / TEST_CASES_SINGLE_FILE[0].target_rel_path
    spec = TorrentSpec(target=target, output=tmp_path, source="my_source")
    _, metainfo, _ = create_torrent(spec)
    assert "source" in metainfo["info"], "metainfo['info'] does not have 'source'"
    assert metainfo["info"]["source"] == "my_source", "metainfo['info']['source'] does not have expected value"

    spec = TorrentSpec(target=target, output=tmp_path, source="%")
    with pytest.raises(ValueError, match="Invalid source"):
        create_torrent(spec)


def test_target_does_not_exist(testdata_dir: Path, tmp_path: Path):
    spec = TorrentSpec(testdata_dir / "non_existent_folder", output=tmp_path)
    with pytest.raises(FileNotFoundError):
        create_torrent(spec)


def test_target_empty(testdata_dir: Path, tmp_path: Path):
    spec = TorrentSpec(testdata_dir / "empty_folder", output=tmp_path)
    with pytest.raises(ValueError, match="Cannot create torrent for 0-byte data"):
        create_torrent(spec)
