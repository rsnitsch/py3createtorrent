#!/usr/bin/env python3
"""
Create torrents via command line!

Copyright (C) 2010-2026 Robert Nitsch
Licensed according to LGPL v3.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import logging
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

try:
    from bencodepy import encode as bencode
except ImportError as exc:
    sys.exit("ERROR: bencodepy module could not be imported.\nPlease install it using: pip install bencode.py")

__version__ = "2.0.0"

logger = logging.getLogger(__name__)

KIB = 2**10
MIB = KIB * KIB
BLOCK_SIZE = 16 * KIB  # BEP 52 fixed leaf block size (16 KiB)
BEST_TRACKERS_URL = "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_best.txt"
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
    trackers: list[str] = field(default_factory=list)
    nodes: list[str] = field(default_factory=list)
    webseeds: list[str] = field(default_factory=list)
    exclude: list[Path] = field(default_factory=list)
    exclude_pattern: list[str] = field(default_factory=list)
    exclude_pattern_ci: list[str] = field(default_factory=list)
    piece_length: int = 0
    private: bool = False
    protocol: ProtocolVersion = ProtocolVersion.HYBRID
    output: Path | None = None
    name: str | None = None
    comment: str | None = None
    source: str | None = None
    date: int | None = None


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
        next_layer = []
        for i in range(0, len(layer), 2):
            next_layer.append(hashlib.sha256(layer[i] + layer[i + 1]).digest())
        layer = next_layer

    return layer[0]


def compute_v2_file_hashes(file_path: Path, piece_length: int) -> tuple[bytes, bytes | None]:
    """
    Compute (pieces_root, piece_layers) for a single non-empty file according to BEP 52.
    """
    blocks_per_piece = piece_length // BLOCK_SIZE
    piece_depth = blocks_per_piece.bit_length() - 1
    file_size = file_path.stat().st_size

    if file_size <= piece_length:
        block_hashes: list[bytes] = []
        with file_path.open("rb") as fh:
            while block := fh.read(BLOCK_SIZE):
                block_hashes.append(hashlib.sha256(block).digest())
        return merkle_root(block_hashes, leaf_depth=0), None

    piece_hashes: list[bytes] = []
    with file_path.open("rb") as fh:
        while True:
            block_hashes = []
            for _ in range(blocks_per_piece):
                block = fh.read(BLOCK_SIZE)
                if not block:
                    break
                block_hashes.append(hashlib.sha256(block).digest())

            if not block_hashes:
                break

            piece_hashes.append(merkle_root(block_hashes, pad_to=blocks_per_piece, leaf_depth=0))

    root = merkle_root(piece_hashes, leaf_depth=piece_depth)
    layers = b"".join(piece_hashes)
    return root, layers


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
            rel_str = str(child.relative_to(target))

            if norm_key in excluded_paths:
                logger.debug("Skipping '%s' due to explicit exclusion.", rel_str)
                continue

            rel_posix = child.relative_to(target).as_posix()
            if any(rx.search(rel_posix) for rx in excluded_patterns):
                logger.debug("Skipping '%s' due to pattern exclusion.", rel_str)
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


def resolve_trackers(raw_trackers: list[str]) -> list[str]:
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
                logger.debug("Fetching top %d trackers from %s", count, BEST_TRACKERS_URL)
                with urllib.request.urlopen(BEST_TRACKERS_URL, timeout=15) as resp:
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


def build_v1_pieces_and_files(
    entries: list[FileEntry],
    piece_length: int,
    is_single_file: bool,
    align_to_piece_boundaries: bool,
) -> tuple[bytes, list[dict[str, Any]] | None]:
    """
    Generate v1 SHA-1 piece hashes and (for multi-file) the 'files' list.
    Inserts BEP 47 '.pad' entries when align_to_piece_boundaries is True (hybrid mode).
    """
    v1_pieces = bytearray()
    v1_files: list[dict[str, Any]] = []
    buffer = bytearray()

    # Find index of the last non-empty file; trailing padding after it is forbidden in BEP 52
    last_non_empty_idx = max((i for i, e in enumerate(entries) if e.size > 0), default=-1)

    for idx, entry in enumerate(entries):
        logger.debug("Hashing v1: %s", "/".join(entry.rel_parts))
        with entry.abs_path.open("rb") as fh:
            while chunk := fh.read(piece_length - len(buffer)):
                buffer.extend(chunk)
                if len(buffer) == piece_length:
                    v1_pieces.extend(hashlib.sha1(buffer).digest())
                    buffer.clear()

        if not is_single_file:
            v1_files.append({"length": entry.size, "path": entry.rel_parts})

            # In hybrid torrents, pad every non-empty file before the last non-empty file
            # to a multiple of piece_length.
            if align_to_piece_boundaries and entry.size > 0 and idx < last_non_empty_idx and len(buffer) > 0:
                pad_len = piece_length - len(buffer)
                buffer.extend(b"\x00" * pad_len)
                v1_pieces.extend(hashlib.sha1(buffer).digest())
                buffer.clear()
                v1_files.append(
                    {
                        "attr": "p",
                        "length": pad_len,
                        "path": [".pad", str(pad_len)],
                    }
                )

    if buffer:
        v1_pieces.extend(hashlib.sha1(buffer).digest())

    return bytes(v1_pieces), (None if is_single_file else v1_files)


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

    trackers = resolve_trackers(spec.trackers)
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

    # 1. BitTorrent v2 metadata
    piece_layers: dict[bytes, bytes] = {}
    if include_v2:
        info["meta version"] = 2
        for entry in entries:
            if entry.size > 0:
                logger.debug("Hashing v2 Merkle tree: %s", "/".join(entry.rel_parts))
                root, layers = compute_v2_file_hashes(entry.abs_path, piece_length)
                entry.v2_pieces_root = root
                if layers is not None:
                    piece_layers[root] = layers

        info["file tree"] = build_file_tree(entries, is_single_file)

    # 2. BitTorrent v1 metadata
    if include_v1:
        v1_pieces, v1_files = build_v1_pieces_and_files(
            entries=entries,
            piece_length=piece_length,
            is_single_file=is_single_file,
            align_to_piece_boundaries=(spec.protocol == ProtocolVersion.HYBRID),
        )
        info["pieces"] = v1_pieces
        if is_single_file:
            info["length"] = total_size
        else:
            info["files"] = v1_files

    # 3. Outer metainfo dictionary
    metainfo: dict[str, Any] = {
        "info": info,
        "created by": f"py3createtorrent v{__version__}",
    }

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

    spec = TorrentSpec(
        target=args.target,
        trackers=args.trackers,
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
