#!/usr/bin/env python3
"""
Integration test runner for py3createtorrent v2.0.0.

Tests v1, v2, and hybrid torrent creation against single-file and multi-file
fixtures, verifies Bencode/BEP-52 metadata invariants, and runs `libtorrent`
verification checks.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

try:
    from bencodepy import decode as bdecode
    from bencodepy import encode as bencode
except ImportError as exc:
    sys.exit(f"ERROR: bencodepy is required to run verification checks: {exc}")

import cachedir_tag

try:
    import libtorrent as lt
except ImportError:
    lt = None  # type: ignore[assignment]

# Adjust import if py3createtorrent.py lives in src/ or project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(PROJECT_ROOT) / "src"))

from create_random_file import create_random_file
from create_random_folder import create_random_folder

from py3createtorrent import ProtocolVersion, TorrentSpec, create_torrent  # noqa: E402

logger = logging.getLogger(__name__)
type BencodeValue = int | bytes | list[BencodeValue] | dict[bytes, BencodeValue]


@dataclass(frozen=True, slots=True)
class TestCase:
    name: str
    target_rel_path: str
    protocol: ProtocolVersion
    piece_size: int = 0


TEST_CASES = [
    TestCase("single_file_16k_v2", "random_file_16k.dat", ProtocolVersion.V2),
    TestCase("single_file_17k_v2", "random_file_17k.dat", ProtocolVersion.V2),
    TestCase("single_file_48k_v2", "random_file_48k.dat", ProtocolVersion.V2),
    TestCase("single_file_64k_v2", "random_file_64k.dat", ProtocolVersion.V2),
    TestCase("single_file_65k_v2", "random_file_65k.dat", ProtocolVersion.V2),
    TestCase("single_file_65k_v2", "random_file_65k.dat", ProtocolVersion.V2, 32),
    TestCase("single_file_100k_v2", "random_file_100k.dat", ProtocolVersion.V2),
    TestCase("single_file_100k_v2", "random_file_100k.dat", ProtocolVersion.V2, 32),
    TestCase("single_file_v1", "random_file_50m.dat", ProtocolVersion.V1),
    TestCase("single_file_v2", "random_file_50m.dat", ProtocolVersion.V2),
    TestCase("single_file_hybrid", "random_file_50m.dat", ProtocolVersion.HYBRID),
    TestCase("multi_file_v1", "random_folder_big_files", ProtocolVersion.V1),
    TestCase("multi_file_v2", "random_folder_big_files", ProtocolVersion.V2),
    TestCase("multi_file_hybrid", "random_folder_big_files", ProtocolVersion.HYBRID),
    TestCase("multi_file_v1", "random_folder_tiny_files", ProtocolVersion.V1),
    TestCase("multi_file_v2", "random_folder_tiny_files", ProtocolVersion.V2),
    TestCase("multi_file_hybrid", "random_folder_tiny_files", ProtocolVersion.HYBRID),
    TestCase("multi_file_hybrid", "random_folder_tiny_files", ProtocolVersion.HYBRID, 16),
    TestCase("multi_file_hybrid", "random_folder_tiny_files", ProtocolVersion.HYBRID, 32),
    TestCase("multi_file_hybrid_with_empty_files", "random_folder_with_empty_files", ProtocolVersion.HYBRID),
    TestCase("multi_file_hybrid_with_subfolder", "random_folder_with_subfolder", ProtocolVersion.HYBRID),
    TestCase("multi_file_hybrid_with_subfolder", "random_folder_with_subfolder", ProtocolVersion.HYBRID, 16),
]


def ensure_testdata_is_generated():
    testdata_path = PROJECT_ROOT / "tests" / "testdata"
    logger.info("Creating fresh set of random testdata here: %s", testdata_path)

    # Empty first. Always start with freshly generated testdata.
    if testdata_path.is_dir():
        shutil.rmtree(testdata_path)

    testdata_path.mkdir()
    cachedir_tag.tag(testdata_path)

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


def run_all_tests(
    testdata_dir: Path,
    keep_artifacts: bool = False,
    require_libtorrent: bool = False,
) -> bool:
    """
    Run the full integration test matrix. Returns True if all tests pass.
    """
    ensure_testdata_is_generated()

    if lt is None:
        msg = "libtorrent is not installed; skipping libtorrent verification."
        if require_libtorrent:
            logger.error(msg)
            return False
        logger.warning(msg)

    tmp_dir = Path(tempfile.mkdtemp(prefix="py3ct_test_"))
    logger.info("Using temporary workspace: %s", tmp_dir)

    passed = 0
    failed = 0

    try:
        for case in TEST_CASES:
            target = testdata_dir / case.target_rel_path
            if not target.exists():
                logger.error("[%s] Missing test fixture: %s", case.name, target)
                failed += 1
                continue

            logger.info("Running test case: %-22s (protocol=%s)", case.name, case.protocol.value)

            try:
                case_dir = tmp_dir / case.name
                case_dir.mkdir(parents=True, exist_ok=True)

                spec = TorrentSpec(
                    target=target,
                    trackers=["best3"],
                    piece_length=case.piece_size,
                    private=False,
                    protocol=case.protocol,
                    output=case_dir,
                )

                torrent_path, _, total_size = create_torrent(spec)
                logger.debug("  Created %s (%d bytes source data)", torrent_path, total_size)

                verify_bencode_invariants(
                    torrent_path=torrent_path,
                    protocol=case.protocol,
                    is_single_file=target.is_file(),
                )

                if lt is not None:
                    verify_with_libtorrent_offline(
                        torrent_path=torrent_path,
                        save_path=target.parent,
                        protocol=case.protocol,
                    )

                logger.info("  [PASS] %s", case.name)
                passed += 1

            except Exception as exc:
                logger.error("  [FAIL] %s: %s", case.name, exc)
                failed += 1

    finally:
        if keep_artifacts:
            logger.info("Keeping generated test artifacts in: %s", tmp_dir)
        else:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    logger.info("Summary: %d passed, %d failed (total %d)", passed, failed, len(TEST_CASES))
    return failed == 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Integration test runner for py3createtorrent v2.0.0",
    )
    parser.add_argument(
        "--testdata",
        type=Path,
        default=PROJECT_ROOT / "tests" / "testdata",
        help="Path to testdata directory containing random_file.dat and random_folder.",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        default=False,
        help="Do not delete temporary generated .torrent files after running.",
    )
    parser.add_argument(
        "--require-libtorrent",
        action="store_true",
        default=False,
        help="Fail the test run if libtorrent is not installed.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose debug logging.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(name)s | [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    success = run_all_tests(
        testdata_dir=args.testdata,
        keep_artifacts=args.keep_artifacts,
        require_libtorrent=args.require_libtorrent,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
