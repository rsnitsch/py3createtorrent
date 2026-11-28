#!/usr/bin/env python3
from __future__ import annotations

import logging
import random
import shutil
import sys
import warnings
from pathlib import Path

import cachedir_tag
import pytest

try:
    import libtorrent as lt
except ImportError:
    lt = None  # type: ignore[assignment]

from py3createtorrent import BLOCK_SIZE, KIB, MIB, READ_CHUNK_SIZE

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTDATA_DIR = PROJECT_ROOT / "tests" / "testdata"
logger = logging.getLogger(__name__)


def ensure_file_with_random_content_exists(path: Path, size_in_bytes: int, seed: int = 0) -> Path:
    """
    Ensure a file exists with the exact requested byte size.
    Does not touch the disk if the file already exists with the expected size.
    """
    if path.is_file() and path.stat().st_size == size_in_bytes:
        return path

    logger.info("Generating test file %s (%d bytes)", path, size_in_bytes)
    path.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    chunk_size = 64 * KIB
    remaining = size_in_bytes

    with path.open("wb") as fh:
        while remaining > 0:
            to_write = min(chunk_size, remaining)
            fh.write(rng.randbytes(to_write))
            remaining -= to_write

    return path


def ensure_folder_with_files_exists(
    path: Path,
    files_with_sizes: dict[str, int],
    seed: int = 0,
) -> Path:
    """
    Ensure a folder contains exactly the specified relative files and sizes.
    Removes any unexpected files or subdirectories to keep the fixture clean.
    """
    path.mkdir(parents=True, exist_ok=True)
    expected_files = {(path / rel_path).resolve(): size for rel_path, size in files_with_sizes.items()}

    # Remove unexpected files or empty directories not part of the spec
    for existing in sorted(path.rglob("*"), reverse=True):
        resolved = existing.resolve()
        if existing.is_file() and resolved not in expected_files:
            logger.info("Removing unexpected file in testdata: %s", existing)
            existing.unlink()
        elif existing.is_dir():
            # Keep directory only if at least one expected file lives inside it
            is_needed = any(existing.resolve() in f.parents for f in expected_files)
            if not is_needed:
                logger.info("Removing unexpected directory in testdata: %s", existing)
                shutil.rmtree(existing)

    # Create or fix expected files
    for idx, (rel_path, size) in enumerate(sorted(files_with_sizes.items())):
        ensure_file_with_random_content_exists(path / rel_path, size, seed=seed + idx)

    return path


@pytest.fixture(scope="session")
def testdata_dir() -> Path:
    """Provide the persistent testdata directory tagged as a cache directory."""
    TESTDATA_DIR.mkdir(parents=True, exist_ok=True)
    if not (TESTDATA_DIR / "CACHEDIR.TAG").exists():
        cachedir_tag.tag(TESTDATA_DIR)
    return TESTDATA_DIR


@pytest.fixture(scope="session")
def sample_file(testdata_dir: Path) -> Path:
    """Provide a small, deterministic single file for fast unit/API tests."""
    return ensure_file_with_random_content_exists(testdata_dir / "sample_16k.dat", BLOCK_SIZE, seed=1)


@pytest.fixture(scope="session")
def empty_folder(testdata_dir: Path) -> Path:
    """Provide a guaranteed empty directory."""
    return ensure_folder_with_files_exists(testdata_dir / "empty_folder", {})


@pytest.fixture(scope="session")
def exclude_test_folder(testdata_dir: Path) -> Path:
    """Provide a small directory with mixed filenames/subfolders for exclusion tests."""
    return ensure_folder_with_files_exists(
        testdata_dir / "folder_for_excludes",
        {
            "keep.txt": KIB,
            "ignore_me.tmp": KIB,
            "README.MD": KIB,
            "sub/nested.log": KIB,
            "sub/data.bin": KIB,
        },
        seed=400,
    )


@pytest.fixture(scope="session")
def integration_testdata(testdata_dir: Path) -> Path:
    """
    Ensure all targeted single-file and multi-file edge-case fixtures exist
    without rewriting already valid files on disk.
    """
    # Single files targeting BLOCK_SIZE (16 KiB), piece_size boundaries, and READ_CHUNK_SIZE (4 MiB)
    single_files = {
        "file_1b.dat": 1,
        "file_16k_exact_block.dat": BLOCK_SIZE,
        "file_16k_plus_1.dat": BLOCK_SIZE + 1,
        "file_32k_exact_piece.dat": 32 * KIB,
        "file_64k_plus_1.dat": 64 * KIB + 1,
        "file_4m_exact_read_chunk.dat": READ_CHUNK_SIZE,
        "file_4m_plus_1.dat": READ_CHUNK_SIZE + 1,
    }
    for idx, (filename, size) in enumerate(single_files.items()):
        ensure_file_with_random_content_exists(testdata_dir / filename, size, seed=100 + idx)

    # Multi-file folder: aligned, unaligned, sub-block, and empty files (start, middle, end)
    ensure_folder_with_files_exists(
        testdata_dir / "folder_edge_cases",
        {
            "00_empty_start.txt": 0,
            "01_tiny_1b.dat": 1,
            "02_exact_16k.dat": BLOCK_SIZE,
            "03_unaligned_17k.dat": 17 * KIB,
            "04_empty_middle.txt": 0,
            "05_exact_32k.dat": 32 * KIB,
            "06_unaligned_50k.dat": 50 * KIB,
            "99_empty_end.txt": 0,
        },
        seed=200,
    )

    # Multi-file folder with nested subdirectories and trailing empty file in subfolder
    ensure_folder_with_files_exists(
        testdata_dir / "folder_nested",
        {
            "root_file.dat": 20 * KIB,
            "sub_a/exact_block.dat": BLOCK_SIZE,
            "sub_a/empty.txt": 0,
            "sub_b/deep/chunk_100k.dat": 100 * KIB,
            "sub_b/deep/empty_at_end.txt": 0,
        },
        seed=300,
    )

    # Multi-file folder exceeding the 16 MiB parallel slice boundary
    ensure_folder_with_files_exists(
        testdata_dir / "folder_multi_slice",
        {
            "file_17m.dat": 17 * MIB,
            "file_1k.dat": KIB,
        },
        seed=350,
    )

    return testdata_dir


@pytest.fixture(scope="session")
def is_libtorrent_present() -> bool:
    if lt is not None:
        return True

    py_ver = sys.version_info[:2]
    if (3, 11) <= py_ver <= (3, 13):
        # Fail tests if libtorrent is missing on supported Python versions
        pytest.fail(f"libtorrent is required on Python {py_ver[0]}.{py_ver[1]}, but could not be imported.")

    warnings.warn(
        f"libtorrent is not installed on Python {py_ver[0]}.{py_ver[1]}; skipping libtorrent offline verification.",
        UserWarning,
        stacklevel=2,
    )
    return False
