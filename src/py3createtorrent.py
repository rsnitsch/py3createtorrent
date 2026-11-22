#!/usr/bin/env python3
"""
Create torrents via command line!

Copyright (C) 2010-2026 Robert Nitsch
Licensed according to LGPL v3.
"""

from __future__ import annotations

import argparse
import datetime
import functools
import hashlib
import logging
import math
import os
import re
import sys
import time
import tomllib
import urllib.error
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any


def _get_version() -> str:
    try:
        # Installed as a package (uv tool, pipx, pip, editable install)
        return version("py3createtorrent")
    except PackageNotFoundError:
        # src/py3createtorrent.py is executed directly
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if pyproject.is_file():
            with pyproject.open("rb") as f:
                data = tomllib.load(f)
            return str(data["project"]["version"])
        return "unknown"


__version__ = _get_version()

try:
    from bencodepy import encode as bencode
except ImportError as exc:
    sys.exit("ERROR: bencodepy module could not be imported.\nPlease install it using: pip install bencode.py")


logger = logging.getLogger(__name__)

KIB = 2**10
MIB = KIB * KIB
BLOCK_SIZE = 16 * KIB  # BEP 52 fixed leaf block size (16 KiB)
READ_CHUNK_SIZE = 4 * MIB  # Cap single read buffer to 4 MiB (always a multiple of BLOCK_SIZE)
DEFAULT_BEST_TRACKERS_URL = "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_best.txt"
NAME_PATTERN = re.compile(r"^[A-Z0-9_\-., ()]+$", re.IGNORECASE)
SOURCE_PATTERN = re.compile(r"^[A-Z0-9_\-., ]+$", re.IGNORECASE)


class ProtocolVersion(StrEnum):
    V1 = "v1"
    V2 = "v2"
    HYBRID = "hybrid"


@dataclass(slots=True)
class FileEntry:
    abs_path: Path
    rel_parts: list[str]
    size: int
    v2_pieces_root: bytes | None = None
    v2_piece_layers: bytes | None = None


@dataclass(slots=True)
class TorrentSpec:
    target: Path
    trackers: list[str] = field(default_factory=list[str])
    best_trackers_url: str = DEFAULT_BEST_TRACKERS_URL
    nodes: list[str] = field(default_factory=list[str])
    webseeds: list[str] = field(default_factory=list[str])
    exclude: list[Path] = field(default_factory=list[Path])
    exclude_pattern: list[str] = field(default_factory=list[str])
    exclude_pattern_ci: list[str] = field(default_factory=list[str])
    piece_length: int = 0
    private: bool = False
    protocol: ProtocolVersion = ProtocolVersion.HYBRID
    output: Path | None = None
    name: str | None = None
    comment: str | None = None
    source: str | None = None
    date: int | None = None
    created_by: bool = True


def is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def calculate_piece_length(size: int) -> int:
    """
    Calculate a power-of-two piece length between 16 KiB and 64 MiB.
    """
    if size <= 0:
        raise ValueError(f"Size must be greater than 0 (got {size})")

    if size < 16 * KIB:
        return 16 * KIB

    piece_length = 256 * KIB

    while size / piece_length > 2000:
        piece_length *= 2

    while size / piece_length < 8:
        piece_length //= 2

    return max(min(piece_length, 64 * MIB), 16 * KIB)


@functools.lru_cache(maxsize=32)
def _zero_subtree_hash(depth: int) -> bytes:
    """
    Compute the BEP 52 zero hash at a given tree depth:
    depth 0 (16 KiB leaf) = 32 zero bytes,
    depth d = SHA256(zero(d-1) || zero(d-1)).
    """
    h = b"\x00" * 32
    for _ in range(depth):
        h = hashlib.sha256(h + h).digest()
    return h


def merkle_root(hashes: list[bytes], pad_to: int | None = None, leaf_depth: int = 0) -> bytes:
    """
    Compute the SHA-256 Merkle tree root according to BEP 52.
    Pads the layer with the appropriate zero-subtree hashes for `leaf_depth`
    up to `pad_to` (if given) or up to the next power of two.
    """
    if not hashes:
        return _zero_subtree_hash(leaf_depth)

    layer = list(hashes)
    target_len = pad_to if pad_to is not None else (1 << (len(layer) - 1).bit_length())

    if len(layer) < target_len:
        pad_hash = _zero_subtree_hash(leaf_depth)
        layer.extend([pad_hash] * (target_len - len(layer)))

    while len(layer) > 1:
        next_layer: list[bytes] = []
        for i in range(0, len(layer), 2):
            next_layer.append(hashlib.sha256(layer[i] + layer[i + 1]).digest())
        layer = next_layer

    return layer[0]


@dataclass(slots=True)
class _ChunkResult:
    v1_hashes: bytes
    v2_piece_hashes: list[bytes]


def _hash_file_slice(
    file_path: Path,
    start_offset: int,
    length: int,
    piece_length: int,
    include_v1: bool,
    include_v2: bool,
    pad_last_piece_v1: bool,
) -> _ChunkResult:
    """
    Worker function executed in a thread pool to hash a piece-aligned byte range
    [start_offset, start_offset + length) of a single file for v1 and/or v2.
    """
    read_size = min(piece_length, READ_CHUNK_SIZE)
    blocks_per_piece = piece_length // BLOCK_SIZE

    v1_pieces = bytearray()
    v1_hasher = hashlib.sha1() if include_v1 else None
    v1_bytes_in_piece = 0

    v2_piece_hashes: list[bytes] = []
    v2_current_piece_blocks: list[bytes] = []
    v2_block_hasher = hashlib.sha256() if include_v2 else None
    v2_bytes_in_block = 0

    remaining = length
    with file_path.open("rb") as fh:
        if start_offset > 0:
            fh.seek(start_offset)

        while remaining > 0:
            chunk = fh.read(min(read_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            mv = memoryview(chunk)

            # 1. v1 SHA-1 piece hashing
            if v1_hasher is not None:
                offset = 0
                while offset < len(mv):
                    needed = piece_length - v1_bytes_in_piece
                    take = min(needed, len(mv) - offset)
                    v1_hasher.update(mv[offset : offset + take])
                    v1_bytes_in_piece += take
                    offset += take

                    if v1_bytes_in_piece == piece_length:
                        v1_pieces.extend(v1_hasher.digest())
                        v1_hasher = hashlib.sha1()
                        v1_bytes_in_piece = 0

            # 2. v2 SHA-256 16 KiB Merkle leaf hashing
            if include_v2 and v2_block_hasher is not None:
                offset = 0
                while offset < len(mv):
                    if v2_bytes_in_block == 0 and (len(mv) - offset) >= BLOCK_SIZE:
                        v2_current_piece_blocks.append(hashlib.sha256(mv[offset : offset + BLOCK_SIZE]).digest())
                        offset += BLOCK_SIZE
                    else:
                        needed = BLOCK_SIZE - v2_bytes_in_block
                        take = min(needed, len(mv) - offset)
                        v2_block_hasher.update(mv[offset : offset + take])
                        v2_bytes_in_block += take
                        offset += take

                        if v2_bytes_in_block == BLOCK_SIZE:
                            v2_current_piece_blocks.append(v2_block_hasher.digest())
                            v2_block_hasher = hashlib.sha256()
                            v2_bytes_in_block = 0

                    if len(v2_current_piece_blocks) == blocks_per_piece:
                        v2_piece_hashes.append(
                            merkle_root(v2_current_piece_blocks, pad_to=blocks_per_piece, leaf_depth=0)
                        )
                        v2_current_piece_blocks.clear()

    # Finalize trailing partial piece at EOF
    if include_v2 and v2_block_hasher is not None:
        if v2_bytes_in_block > 0:
            v2_current_piece_blocks.append(v2_block_hasher.digest())
        if v2_current_piece_blocks:
            # Note: for files < piece_length, caller will compute root directly from unpadded blocks
            # if length < piece_length and start_offset == 0; otherwise pad to blocks_per_piece.
            if start_offset == 0 and length < piece_length:
                v2_piece_hashes.append(merkle_root(v2_current_piece_blocks, leaf_depth=0))
            else:
                v2_piece_hashes.append(merkle_root(v2_current_piece_blocks, pad_to=blocks_per_piece, leaf_depth=0))

    if v1_hasher is not None and v1_bytes_in_piece > 0:
        if pad_last_piece_v1:
            pad_len = piece_length - v1_bytes_in_piece
            zero_mv = memoryview(b"\x00" * min(pad_len, read_size))
            rem_pad = pad_len
            while rem_pad > 0:
                step = min(rem_pad, len(zero_mv))
                v1_hasher.update(zero_mv[:step])
                rem_pad -= step
        v1_pieces.extend(v1_hasher.digest())

    return _ChunkResult(v1_hashes=bytes(v1_pieces), v2_piece_hashes=v2_piece_hashes)


def _hash_v1_unaligned_stream(
    entries: list[FileEntry],
    piece_length: int,
    is_single_file: bool,
    executor: ThreadPoolExecutor,
) -> tuple[bytes, list[dict[str, Any]] | None]:
    """
    Parallel v1 hashing when files are concatenated without piece alignment (pure v1 mode).
    Reads sequentially into piece-sized buffers and hashes pieces across worker threads.
    """
    v1_files: list[dict[str, Any]] = []
    futures: list[Future[bytes]] = []
    buffer = bytearray()

    def _sha1_digest(data: bytes) -> bytes:
        return hashlib.sha1(data).digest()

    for entry in entries:
        logger.debug("Hashing v1 stream: %s", "/".join(entry.rel_parts))
        if not is_single_file:
            v1_files.append({"length": entry.size, "path": entry.rel_parts})

        if entry.size > 0:
            with entry.abs_path.open("rb") as fh:
                while chunk := fh.read(piece_length - len(buffer)):
                    buffer.extend(chunk)
                    if len(buffer) == piece_length:
                        piece_bytes = bytes(buffer)
                        buffer.clear()
                        futures.append(executor.submit(_sha1_digest, piece_bytes))

    if buffer:
        last_bytes = bytes(buffer)
        futures.append(executor.submit(_sha1_digest, last_bytes))

    v1_pieces = b"".join(f.result() for f in futures)
    return v1_pieces, (None if is_single_file else v1_files)


def hash_files(
    entries: list[FileEntry],
    piece_length: int,
    is_single_file: bool,
    include_v1: bool,
    include_v2: bool,
    align_to_piece_boundaries: bool,
    max_workers: int | None = None,
) -> tuple[bytes | None, list[dict[str, Any]] | None, dict[bytes, bytes]]:
    """
    Hash all files in a single pass over disk I/O using a ThreadPoolExecutor,
    computing v1 SHA-1 pieces/files and/or v2 SHA-256 Merkle roots and piece layers.
    """
    workers = max_workers or min(32, (os.cpu_count() or 4))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Pure v1 multi-file torrents concatenate files without piece-boundary padding
        if include_v1 and not include_v2 and not align_to_piece_boundaries and not is_single_file:
            v1_pieces, v1_files_stream = _hash_v1_unaligned_stream(entries, piece_length, is_single_file, executor)
            return v1_pieces, v1_files_stream, {}

        blocks_per_piece = piece_length // BLOCK_SIZE
        piece_depth = blocks_per_piece.bit_length() - 1
        last_non_empty_idx = max((i for i, e in enumerate(entries) if e.size > 0), default=-1)

        # Target ~16 MiB per parallel slice for large files, always aligned to piece_length
        pieces_per_slice = max(1, (16 * MIB) // piece_length)
        slice_bytes = pieces_per_slice * piece_length

        # Submit all slice tasks across all files
        file_tasks: list[tuple[int, FileEntry, list[Any], bool]] = []
        for idx, entry in enumerate(entries):
            logger.debug("Scheduling hash tasks: %s", "/".join(entry.rel_parts))
            if entry.size == 0:
                file_tasks.append((idx, entry, [], False))
                continue

            needs_v1_pad = (
                include_v1
                and align_to_piece_boundaries
                and not is_single_file
                and idx < last_non_empty_idx
                and (entry.size % piece_length != 0)
            )

            futures: list[Future[_ChunkResult]] = []
            offset = 0
            while offset < entry.size:
                chunk_len = min(slice_bytes, entry.size - offset)
                is_last_slice = (offset + chunk_len) == entry.size
                futures.append(
                    executor.submit(
                        _hash_file_slice,
                        entry.abs_path,
                        offset,
                        chunk_len,
                        piece_length,
                        include_v1,
                        include_v2,
                        needs_v1_pad and is_last_slice,
                    )
                )
                offset += chunk_len

            file_tasks.append((idx, entry, futures, needs_v1_pad))

        # Collect results in deterministic file/offset order
        v1_pieces = bytearray()
        v1_files: list[dict[str, Any]] = []
        piece_layers: dict[bytes, bytes] = {}

        for idx, entry, futures, needs_v1_pad in file_tasks:
            if include_v1 and not is_single_file:
                v1_files.append({"length": entry.size, "path": entry.rel_parts})

            if entry.size == 0:
                continue

            all_v2_piece_hashes: list[bytes] = []
            for fut in futures:
                res: _ChunkResult = fut.result()
                if include_v1:
                    v1_pieces.extend(res.v1_hashes)
                if include_v2:
                    all_v2_piece_hashes.extend(res.v2_piece_hashes)

            if include_v1 and needs_v1_pad:
                pad_len = piece_length - (entry.size % piece_length)
                v1_files.append(
                    {
                        "attr": "p",
                        "length": pad_len,
                        "path": [".pad", str(pad_len)],
                    }
                )

            if include_v2:
                if entry.size <= piece_length:
                    # Single-piece (or sub-piece) file: all_v2_piece_hashes[0] is already the root
                    entry.v2_pieces_root = all_v2_piece_hashes[0]
                else:
                    root = merkle_root(all_v2_piece_hashes, leaf_depth=piece_depth)
                    entry.v2_pieces_root = root
                    if len(all_v2_piece_hashes) > 1:
                        piece_layers[root] = b"".join(all_v2_piece_hashes)

    return (
        bytes(v1_pieces) if include_v1 else None,
        (None if (not include_v1 or is_single_file) else v1_files),
        piece_layers,
    )


def _normalize_path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def compile_exclude_rules(
    target: Path,
    exclude: list[Path],
    exclude_pattern: list[str],
    exclude_pattern_ci: list[str],
) -> tuple[set[str], list[re.Pattern[str]]]:
    """
    Validate and compile explicit path exclusions and regular expression exclusions.
    """
    excluded_paths: set[str] = set()
    for path in exclude:
        if not path.exists():
            logger.warning("You're excluding a path that does not exist: '%s'", path)
        excluded_paths.add(_normalize_path_key(path))

    compiled_patterns: list[re.Pattern[str]] = []
    for raw_pattern in exclude_pattern:
        try:
            compiled_patterns.append(re.compile(raw_pattern))
        except re.error as exc:
            raise ValueError(f"Invalid regular expression '{raw_pattern}': {exc}") from exc

    for raw_pattern in exclude_pattern_ci:
        try:
            compiled_patterns.append(re.compile(raw_pattern, re.IGNORECASE))
        except re.error as exc:
            raise ValueError(f"Invalid case-insensitive regular expression '{raw_pattern}': {exc}") from exc

    if target.is_file() and (excluded_paths or compiled_patterns):
        logger.warning("Excluding paths is not possible when creating a torrent for a single file.")

    return excluded_paths, compiled_patterns


def scan_target(
    target: Path,
    excluded_paths: set[str] | None = None,
    excluded_patterns: list[re.Pattern[str]] | None = None,
) -> list[FileEntry]:
    """
    Scan target file or directory and return FileEntry items sorted by raw UTF-8
    path component bytes, matching BEP 52's bencoded 'file tree' traversal order.
    """
    if target.is_file():
        return [FileEntry(abs_path=target, rel_parts=[target.name], size=target.stat().st_size)]

    if not target.is_dir():
        raise FileNotFoundError(f"Target '{target}' is neither a file nor a directory.")

    excluded_paths = excluded_paths or set()
    excluded_patterns = excluded_patterns or []

    root_resolved = target.resolve()
    if _normalize_path_key(root_resolved) in excluded_paths:
        raise ValueError(f"Cannot exclude the target directory itself: '{target}'")

    entries: list[FileEntry] = []
    visited_dirs: set[Path] = set()

    def _walk(current_dir: Path) -> None:
        resolved_dir = current_dir.resolve()
        if resolved_dir in visited_dirs:
            logger.warning("Skipping symlink '%s', because its target has already been processed.", current_dir)
            return
        visited_dirs.add(resolved_dir)

        children = sorted(current_dir.iterdir(), key=lambda p: p.name.encode("utf-8"))
        for child in children:
            norm_key = _normalize_path_key(child)
            rel_posix = child.relative_to(target).as_posix()

            if norm_key in excluded_paths:
                logger.debug("Skipping '%s' due to explicit exclusion.", rel_posix)
                continue

            if any(rx.search(rel_posix) for rx in excluded_patterns):
                logger.debug("Skipping '%s' due to pattern exclusion.", rel_posix)
                continue

            if child.is_dir():
                _walk(child)
            elif child.is_file():
                rel_parts = list(child.relative_to(target).parts)
                entries.append(FileEntry(abs_path=child, rel_parts=rel_parts, size=child.stat().st_size))

    _walk(target)
    return entries


def resolve_output_path(output: Path | None, torrent_name: str) -> Path:
    default_filename = f"{torrent_name}.torrent"
    if output is None:
        return Path.cwd() / default_filename

    resolved = output.resolve()
    if resolved.is_dir():
        return resolved / default_filename

    if not resolved.parent.is_dir():
        raise FileNotFoundError(f"Output directory does not exist: {resolved.parent}")

    return resolved


def resolve_trackers(raw_trackers: list[str], best_trackers_url: str) -> list[str]:
    """
    Expand 'bestN' shortcuts and deduplicate tracker URLs while preserving order.
    """
    best_pattern = re.compile(r"^best(\d+)$", re.IGNORECASE)
    resolved: list[str] = []

    for tracker in raw_trackers:
        match = best_pattern.match(tracker.strip())
        if match:
            count = int(match.group(1))
            if count > 0:
                if not best_trackers_url.strip():
                    raise ValueError("Best trackers URL must not be empty.")
                logger.debug("Fetching top %d trackers from %s", count, best_trackers_url)
                with urllib.request.urlopen(best_trackers_url.strip(), timeout=15) as resp:
                    lines = [line.strip() for line in resp.read().decode("utf-8").splitlines() if line.strip()]
                resolved.extend(lines[:count])
        else:
            resolved.append(tracker.strip())

    # Deduplicate preserving order
    return list(dict.fromkeys(resolved))


def parse_nodes(raw_nodes: list[str], private: bool) -> list[list[str | int]]:
    """
    Validate and parse DHT bootstrap nodes given as 'host,port'.
    """
    if raw_nodes and private:
        raise ValueError(
            "DHT bootstrap nodes cannot be specified for a private torrent. Private torrents do not support DHT."
        )

    parsed: list[list[str | int]] = []
    for raw in raw_nodes:
        parts = raw.split(",")
        if len(parts) != 2 or not parts[0].strip():
            raise ValueError(f"Invalid format for DHT bootstrap node '{raw}'. Please use the format 'host,port'.")
        host = parts[0].strip()
        port_str = parts[1].strip()
        if not port_str.isdigit():
            raise ValueError(f"Invalid port number for DHT bootstrap node '{raw}'. Ports must be numeric.")
        port = int(port_str)
        if not (1 <= port <= 65535):
            raise ValueError(f"Port number out of range (1-65535) for DHT bootstrap node '{raw}'.")
        parsed.append([host, port])

    return parsed


def build_file_tree(entries: list[FileEntry], is_single_file: bool) -> dict[str, Any]:
    """
    Construct the BEP 52 'file tree' nested dictionary structure.
    """
    tree: dict[str, Any] = {}

    for entry in entries:
        # In single-file v2 torrents, the root key is still the file's name
        parts = entry.rel_parts
        current = tree
        for part in parts[:-1]:
            current = current.setdefault(part, {})

        leaf_meta: dict[str, Any] = {"length": entry.size}
        if entry.size > 0 and entry.v2_pieces_root is not None:
            leaf_meta["pieces root"] = entry.v2_pieces_root

        current[parts[-1]] = {"": leaf_meta}

    return tree


def create_torrent(spec: TorrentSpec) -> tuple[Path, dict[str, Any], int]:
    """
    Build the metainfo dictionary and write the .torrent file to disk.
    """
    parsed_nodes = parse_nodes(spec.nodes, spec.private)
    excluded_paths, excluded_patterns = compile_exclude_rules(
        target=spec.target,
        exclude=spec.exclude,
        exclude_pattern=spec.exclude_pattern,
        exclude_pattern_ci=spec.exclude_pattern_ci,
    )
    entries = scan_target(
        spec.target,
        excluded_paths=excluded_paths,
        excluded_patterns=excluded_patterns,
    )
    total_size = sum(e.size for e in entries)

    if total_size == 0:
        raise ValueError("Cannot create torrent for 0-byte data. Check your files and exclusions!")

    if spec.piece_length == 0:
        piece_length = calculate_piece_length(total_size)
        logger.debug("Calculated piece length: %d KiB", piece_length // KIB)
    else:
        piece_length = spec.piece_length * KIB
        if piece_length < 16 * KIB or not is_power_of_two(piece_length):
            raise ValueError("Piece length must be a power of two and at least 16 KiB.")

    trackers = resolve_trackers(spec.trackers, spec.best_trackers_url)
    webseeds = list(dict.fromkeys(w.strip() for w in spec.webseeds if w.strip()))
    is_single_file = spec.target.is_file()
    include_v1 = spec.protocol in (ProtocolVersion.V1, ProtocolVersion.HYBRID)
    include_v2 = spec.protocol in (ProtocolVersion.V2, ProtocolVersion.HYBRID)

    if spec.name is not None:
        torrent_name = spec.name.strip()
        if not torrent_name or not NAME_PATTERN.match(torrent_name):
            raise ValueError(
                f"Invalid name: '{spec.name}'. Allowed chars: A-Z, a-z, 0-9, any of {{.,_-()}} plus spaces."
            )
        if is_single_file:
            entries[0].rel_parts = [torrent_name]
    else:
        torrent_name = spec.target.resolve().name

    info: dict[str, Any] = {
        "name": torrent_name,
        "piece length": piece_length,
    }

    if spec.private:
        info["private"] = 1

    if spec.source is not None:
        source = spec.source.strip()
        if not source or not SOURCE_PATTERN.match(source):
            raise ValueError(
                f"Invalid source: '{spec.source}'. Allowed chars: A-Z, a-z, 0-9, any of {{.,_-}} plus spaces."
            )
        info["source"] = source

    # 1. Hash the files for v1 and/or v2.
    v1_pieces, v1_files, piece_layers = hash_files(
        entries=entries,
        piece_length=piece_length,
        is_single_file=is_single_file,
        include_v1=include_v1,
        include_v2=include_v2,
        align_to_piece_boundaries=(spec.protocol == ProtocolVersion.HYBRID),
    )

    if include_v2:
        info["meta version"] = 2
        info["file tree"] = build_file_tree(entries, is_single_file)

    if include_v1:
        assert v1_pieces is not None
        info["pieces"] = v1_pieces
        if is_single_file:
            info["length"] = total_size
        else:
            info["files"] = v1_files

    # 2. Outer metainfo dictionary
    metainfo: dict[str, Any] = {
        "info": info,
    }

    if spec.created_by:
        metainfo["created by"] = f"py3createtorrent v{__version__}"

    if spec.date is None or spec.date == -1:
        metainfo["creation date"] = int(time.time())
    elif spec.date >= 0:
        metainfo["creation date"] = spec.date
    elif spec.date != -2:
        raise ValueError(
            "Invalid date: Negative timestamp values are not allowed "
            "(use -1 or None for current date, or -2 to omit creation date)."
        )

    if spec.comment:
        metainfo["comment"] = spec.comment

    if include_v2:
        metainfo["piece layers"] = piece_layers

    if trackers:
        metainfo["announce"] = trackers[0]
        if len(trackers) > 1:
            metainfo["announce-list"] = [[t] for t in trackers]

    if parsed_nodes:
        metainfo["nodes"] = parsed_nodes

    if webseeds:
        metainfo["url-list"] = webseeds

    output_path = resolve_output_path(spec.output, info["name"])
    logger.debug("Writing torrent file to: %s", output_path)
    output_path.write_bytes(bencode(metainfo))

    return output_path, metainfo, total_size


def print_summary(metainfo: dict[str, Any], total_size: int, protocol: ProtocolVersion) -> None:
    """
    Print the classic py3createtorrent summary to stdout.
    """
    print("Successfully created torrent:")

    if "announce-list" in metainfo:
        backup_list = sorted(metainfo["announce-list"][1:], key=lambda x: x[0].lower())
        backup_trackers = "\n".join(f"    {t[0]}" for t in backup_list)
    else:
        backup_trackers = "    (none)"

    piece_length = metainfo["info"]["piece length"]
    piece_count = math.ceil(total_size / piece_length)

    if total_size > 10 * MIB:
        size_str = f"{total_size / MIB:.2f} MiB"
    else:
        size_str = f"{total_size // KIB} KiB"

    if "creation date" in metainfo:
        creation_date = datetime.datetime.fromtimestamp(metainfo["creation date"]).isoformat(" ")
    else:
        creation_date = "(none)"

    is_private = "yes" if metainfo["info"].get("private") == 1 else "no"

    print(
        f"  Name:                {metainfo['info']['name']}\n"
        f"  Protocol:            {protocol.value}\n"
        f"  Size:                {size_str}\n"
        f"  Pieces:              {piece_count} x {piece_length // KIB} KiB\n"
        f"  Comment:             {metainfo.get('comment', '(none)')}\n"
        f"  Private:             {is_private}\n"
        f"  Creation date:       {creation_date}\n"
        f"  DHT bootstrap nodes: {metainfo.get('nodes', '(none)')}\n"
        f"  Webseeds:            {metainfo.get('url-list', '(none)')}\n"
        f"  Primary tracker:     {metainfo.get('announce', '(none)')}\n"
        f"  Backup trackers:\n"
        f"{backup_trackers}"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="py3createtorrent is a command line utility for creating torrents (v1, v2, hybrid).",
        usage="%(prog)s <target> [-t tracker_url] [options ...]",
        epilog=f"You are using py3createtorrent v{__version__}",
    )

    parser.add_argument(
        "target",
        type=Path,
        help="File or folder for which to create a torrent",
    )
    parser.add_argument(
        "-t",
        "--tracker",
        metavar="TRACKER_URL",
        action="append",
        dest="trackers",
        default=[],
        help="Add one or multiple tracker (announce) URLs (supports 'bestN').",
    )
    parser.add_argument(
        "--best-trackers-url",
        metavar="URL",
        type=str,
        default=DEFAULT_BEST_TRACKERS_URL,
        help=f"URL used to fetch trackers when using 'bestN'. [default: {DEFAULT_BEST_TRACKERS_URL}]",
    )
    parser.add_argument(
        "--node",
        metavar="HOST,PORT",
        action="append",
        dest="nodes",
        default=[],
        help="Add one or multiple DHT bootstrap nodes.",
    )
    parser.add_argument(
        "--webseed",
        metavar="WEBSEED_URL",
        action="append",
        dest="webseeds",
        default=[],
        help="Add one or multiple HTTP/FTP URLs as seeds (GetRight-style).",
    )
    parser.add_argument(
        "-p",
        "--piece-length",
        type=int,
        default=0,
        help="Set piece size in KiB (must be a power of two). [default: 0 = automatic]",
    )
    parser.add_argument(
        "-P",
        "--private",
        action="store_true",
        default=False,
        help="Set the private flag to disable DHT and PEX.",
    )
    parser.add_argument(
        "--protocol",
        type=ProtocolVersion,
        choices=list(ProtocolVersion),
        default=ProtocolVersion.HYBRID,
        help="BitTorrent protocol version to generate. [default: hybrid]",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        metavar="PATH",
        help="Set the filename and/or output directory of the created file. [default: <name>.torrent]",
    )
    parser.add_argument(
        "-e",
        "--exclude",
        type=Path,
        action="append",
        dest="exclude",
        default=[],
        metavar="PATH",
        help="Exclude a specific path (can be repeated to exclude multiple paths).",
    )
    parser.add_argument(
        "--exclude-pattern",
        type=str,
        action="append",
        dest="exclude_pattern",
        default=[],
        metavar="REGEXP",
        help="Exclude paths matching a regular expression (can be repeated to use multiple patterns).",
    )
    parser.add_argument(
        "--exclude-pattern-ci",
        type=str,
        action="append",
        dest="exclude_pattern_ci",
        default=[],
        metavar="REGEXP",
        help="Same as --exclude-pattern but case-insensitive.",
    )
    parser.add_argument(
        "-n",
        "--name",
        type=str,
        default=None,
        help="Set the name of the torrent. [default: <basename of target>]",
    )
    parser.add_argument(
        "-c",
        "--comment",
        type=str,
        default=None,
        help="Add a comment.",
    )
    parser.add_argument(
        "-s",
        "--source",
        type=str,
        default=None,
        help="Add a source tag.",
    )
    parser.add_argument(
        "-d",
        "--date",
        type=int,
        default=-1,
        metavar="TIMESTAMP",
        help="Overwrite creation date. Expects a unix timestamp. "
        "Specify -2 to disable creation date completely. [default: -1 = current date and time]",
    )
    parser.add_argument(
        "--no-created-by",
        action="store_true",
        default=False,
        help="Omit the 'created by' field from the torrent metainfo.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Enable debug logging output.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"py3createtorrent v{__version__}",
    )

    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    logger.debug("py3createtorrent version: %s", __version__)

    spec = TorrentSpec(
        target=args.target,
        trackers=args.trackers,
        best_trackers_url=args.best_trackers_url,
        nodes=args.nodes,
        webseeds=args.webseeds,
        exclude=args.exclude,
        exclude_pattern=args.exclude_pattern,
        exclude_pattern_ci=args.exclude_pattern_ci,
        piece_length=args.piece_length,
        private=args.private,
        protocol=args.protocol,
        output=args.output,
        name=args.name,
        comment=args.comment,
        source=args.source,
        date=args.date,
        created_by=not args.no_created_by,
    )

    try:
        _, metainfo, total_size = create_torrent(spec)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        logger.error("%s", exc)
        sys.exit(1)

    print_summary(metainfo, total_size, spec.protocol)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        sys.exit(130)
