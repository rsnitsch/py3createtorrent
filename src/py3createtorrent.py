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
    piece_length: int = 0
    private: bool = False
    protocol: ProtocolVersion = ProtocolVersion.HYBRID


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


def merkle_root(hashes: list[bytes]) -> bytes:
    """
    Compute the SHA-256 Merkle tree root according to BEP 52.
    Pads the leaf layer with 32-byte zero hashes up to the next power of two.
    """
    if not hashes:
        return b"\x00" * 32

    layer = list(hashes)
    target_len = 1 << (len(layer) - 1).bit_length()
    if len(layer) < target_len:
        layer.extend([b"\x00" * 32] * (target_len - len(layer)))

    while len(layer) > 1:
        next_layer = []
        for i in range(0, len(layer), 2):
            combined = layer[i] + layer[i + 1]
            next_layer.append(hashlib.sha256(combined).digest())
        layer = next_layer

    return layer[0]


def compute_v2_file_hashes(file_path: Path, piece_length: int) -> tuple[bytes, bytes | None]:
    """
    Compute (pieces_root, piece_layers) for a single non-empty file according to BEP 52.
    """
    blocks_per_piece = piece_length // BLOCK_SIZE
    piece_hashes: list[bytes] = []

    with file_path.open("rb") as fh:
        while True:
            block_hashes: list[bytes] = []
            for _ in range(blocks_per_piece):
                block = fh.read(BLOCK_SIZE)
                if not block:
                    break
                block_hashes.append(hashlib.sha256(block).digest())

            if not block_hashes:
                break

            # Pad incomplete trailing piece blocks only if there are multiple pieces,
            # or let merkle_root pad to the next power of two.
            if len(block_hashes) < blocks_per_piece and piece_hashes:
                block_hashes.extend([b"\x00" * 32] * (blocks_per_piece - len(block_hashes)))

            piece_hashes.append(merkle_root(block_hashes))

    root = merkle_root(piece_hashes)
    layers = b"".join(piece_hashes) if len(piece_hashes) > 1 else None
    return root, layers


def scan_target(target: Path) -> list[FileEntry]:
    """
    Scan target file or directory and return deterministically sorted FileEntry items.
    """
    if target.is_file():
        return [FileEntry(abs_path=target, rel_parts=[target.name], size=target.stat().st_size)]

    if not target.is_dir():
        raise FileNotFoundError(f"Target '{target}' is neither a file nor a directory.")

    entries: list[FileEntry] = []
    # Sort case-insensitively across path parts for deterministic torrent layout
    all_files = sorted(
        (p for p in target.rglob("*") if p.is_file()),
        key=lambda p: [part.lower() for part in p.relative_to(target).parts],
    )

    for file_path in all_files:
        rel_parts = list(file_path.relative_to(target).parts)
        entries.append(FileEntry(abs_path=file_path, rel_parts=rel_parts, size=file_path.stat().st_size))

    return entries


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

            # In hybrid torrents, pad every file (except the last) to a multiple of piece_length
            if align_to_piece_boundaries and idx < len(entries) - 1 and len(buffer) > 0:
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
    entries = scan_target(spec.target)
    total_size = sum(e.size for e in entries)

    if total_size == 0:
        raise ValueError("Cannot create torrent for 0-byte data.")

    if spec.piece_length == 0:
        piece_length = calculate_piece_length(total_size)
        logger.debug("Calculated piece length: %d KiB", piece_length // KIB)
    else:
        piece_length = spec.piece_length * KIB
        if piece_length < 16 * KIB or not is_power_of_two(piece_length):
            raise ValueError("Piece length must be a power of two and at least 16 KiB.")

    trackers = resolve_trackers(spec.trackers)
    is_single_file = spec.target.is_file()
    include_v1 = spec.protocol in (ProtocolVersion.V1, ProtocolVersion.HYBRID)
    include_v2 = spec.protocol in (ProtocolVersion.V2, ProtocolVersion.HYBRID)

    info: dict[str, Any] = {
        "name": spec.target.resolve().name,
        "piece length": piece_length,
    }

    if spec.private:
        info["private"] = 1

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
        "creation date": int(time.time()),
        "created by": f"py3createtorrent v{__version__}",
    }

    if include_v2:
        metainfo["piece layers"] = piece_layers

    if trackers:
        metainfo["announce"] = trackers[0]
        if len(trackers) > 1:
            metainfo["announce-list"] = [[t] for t in trackers]

    output_path = Path.cwd() / f"{info['name']}.torrent"
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

    creation_date = datetime.datetime.fromtimestamp(metainfo["creation date"]).isoformat(" ")
    is_private = "yes" if metainfo["info"].get("private") == 1 else "no"

    print(
        f"  Name:                {metainfo['info']['name']}\n"
        f"  Protocol:            {protocol.value}\n"
        f"  Size:                {size_str}\n"
        f"  Pieces:              {piece_count} x {piece_length // KIB} KiB\n"
        f"  Private:             {is_private}\n"
        f"  Creation date:       {creation_date}\n"
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
        piece_length=args.piece_length,
        private=args.private,
        protocol=args.protocol,
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
