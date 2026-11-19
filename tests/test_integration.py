#!/usr/bin/env python3
"""
Integration test runner for py3createtorrent v2.0.0.

Tests v1, v2, and hybrid torrent creation against single-file and multi-file
fixtures, verifies Bencode/BEP-52 metadata invariants, and runs `uvx torrentfile`
as well as `libtorrent` verification checks.
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

try:
    from bencodepy import decode as bdecode
    from bencodepy import encode as bencode
except ImportError as exc:
    sys.exit(f"ERROR: bencodepy is required to run verification checks: {exc}")

try:
    import libtorrent as lt
except ImportError:
    lt = None  # type: ignore[assignment]

# Adjust import if py3createtorrent.py lives in src/ or project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(PROJECT_ROOT) / "src"))

from py3createtorrent import ProtocolVersion, TorrentSpec, create_torrent  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TestCase:
    name: str
    target_rel_path: str
    protocol: ProtocolVersion


TEST_CASES = [
    TestCase("single_file_v1", "random_file.dat", ProtocolVersion.V1),
    TestCase("single_file_v2", "random_file.dat", ProtocolVersion.V2),
    TestCase("single_file_hybrid", "random_file.dat", ProtocolVersion.HYBRID),
    TestCase("multi_file_v1", "random_folder", ProtocolVersion.V1),
    TestCase("multi_file_v2", "random_folder", ProtocolVersion.V2),
    TestCase("multi_file_hybrid", "random_folder", ProtocolVersion.HYBRID),
]


def verify_bencode_invariants(torrent_path: Path, protocol: ProtocolVersion, is_single_file: bool) -> None:
    """
    Verify structural and cryptographic invariants of the generated .torrent file
    according to BEP 3 and BEP 52.
    """
    raw_bytes = torrent_path.read_bytes()
    meta = bdecode(raw_bytes)
    assert isinstance(meta, dict), "Top-level torrent structure must be a dict"

    # Check trackers from best3
    assert b"announce" in meta, "Missing 'announce' key"
    assert b"announce-list" in meta, "Missing 'announce-list' key for best3 trackers"
    assert len(meta[b"announce-list"]) == 3, f"Expected 3 trackers, got {len(meta[b'announce-list'])}"

    info = meta[b"info"]
    assert isinstance(info, dict), "'info' must be a dict"
    info_bencoded = bencode(info)

    if protocol in (ProtocolVersion.V1, ProtocolVersion.HYBRID):
        v1_infohash = hashlib.sha1(info_bencoded).hexdigest()
        logger.debug("  v1 infohash: %s", v1_infohash)
        assert b"pieces" in info, "v1/hybrid torrent missing 'pieces'"
        assert len(info[b"pieces"]) % 20 == 0, "v1 'pieces' length must be a multiple of 20"

        if is_single_file:
            assert b"length" in info and b"files" not in info
        else:
            assert b"files" in info and b"length" not in info
            if protocol == ProtocolVersion.HYBRID:
                pad_entries = [f for f in info[b"files"] if f.get(b"attr") == b"p" and f[b"path"][0] == b".pad"]
                logger.debug("  Hybrid BEP-47 pad files count: %d", len(pad_entries))
    else:
        assert b"pieces" not in info, "Pure v2 torrent must not contain v1 'pieces'"
        assert b"files" not in info, "Pure v2 torrent must not contain v1 'files'"

    if protocol in (ProtocolVersion.V2, ProtocolVersion.HYBRID):
        v2_infohash = hashlib.sha256(info_bencoded).hexdigest()
        logger.debug("  v2 infohash: %s", v2_infohash)
        assert info.get(b"meta version") == 2, "v2/hybrid torrent must have 'meta version' == 2"
        assert b"file tree" in info, "v2/hybrid torrent missing 'file tree'"
        assert b"piece layers" in meta, "v2/hybrid torrent missing 'piece layers'"
    else:
        assert b"meta version" not in info, "Pure v1 torrent must not contain 'meta version'"
        assert b"file tree" not in info, "Pure v1 torrent must not contain 'file tree'"
        assert b"piece layers" not in meta, "Pure v1 torrent must not contain 'piece layers'"


def run_external_torrentfile_check(torrent_path: Path, data_path: Path) -> None:
    """
    Execute `uvx torrentfile recheck` against the generated torrent and source data.
    """
    if shutil.which("uvx") is None:
        raise RuntimeError("'uvx' executable not found in PATH.")

    cmd = ["uvx", "torrentfile", "recheck", str(torrent_path), str(data_path)]
    logger.debug("Running external command: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.stdout.strip():
        logger.debug("torrentfile stdout:\n%s", result.stdout.strip())
    if result.stderr.strip():
        logger.debug("torrentfile stderr:\n%s", result.stderr.strip())

    if result.returncode != 0:
        raise AssertionError(
            f"`torrentfile recheck` failed (exit code {result.returncode}) for {torrent_path.name}:\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )


def verify_with_libtorrent_offline(
    torrent_path: Path,
    save_path: Path,
    protocol: ProtocolVersion,
) -> None:
    """
    Verify torrent metadata and local payload hashes using libtorrent in strict
    offline mode (no listening sockets, no DHT/LSD/UPnP, no tracker announces).
    """
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
    ses.pause()  # Keeps the entire session paused at network level

    params = lt.add_torrent_params()
    params.ti = ti
    params.save_path = str(save_path.resolve())
    # Prevent automatic unpausing and force a full hash recheck instead of trusting seed_mode
    params.flags &= ~lt.torrent_flags.auto_managed
    params.flags &= ~lt.torrent_flags.seed_mode
    params.flags |= lt.torrent_flags.paused

    handle = ses.add_torrent(params)
    handle.force_recheck()

    # Wait briefly until checking actually starts or finishes
    while True:
        s = handle.status()
        if s.errc:
            raise AssertionError(f"libtorrent verification error for {torrent_path.name}: {s.errc.message()}")
        if s.state not in (
            lt.torrent_status.checking_files,
            lt.torrent_status.checking_resume_data,
        ):
            # Guard against reading status before force_recheck transitions out of paused
            if s.progress == 1.0 or s.num_pieces > 0:
                break
        time.sleep(0.05)

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
    if not testdata_dir.is_dir():
        logger.error("Testdata directory does not exist: %s", testdata_dir)
        return False

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
                    piece_length=0,
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
                run_external_torrentfile_check(torrent_path=torrent_path, data_path=target)

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
        format="%(asctime)s [%(levelname)s] %(message)s",
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
