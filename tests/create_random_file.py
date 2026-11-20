"""
Script to create files of given size with pseudo-random content.
"""

import argparse
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_size(size: str):
    letter_to_unit = {"K": 2**10, "M": 2**20, "G": 2**30}

    error_message = (
        "must be a number ending with a single letter to "
        "indicate the unit type K, M or G - for example, use 256k to specify 256 KiB"
    )

    letter = size[-1]
    if letter.isdigit():
        raise argparse.ArgumentTypeError(error_message)

    number = size[:-1]
    if not number.isdigit():
        raise argparse.ArgumentTypeError(error_message)

    return letter_to_unit[letter.upper()] * int(number)


def create_random_file(path: Path, size: int, seed: int = 0, overwrite: bool = False) -> bool:
    if size < 0:
        raise ValueError("size is negative")

    if path.is_file() and not overwrite:
        logger.warning("Destination file %s already exists - skipping.", path)
        return False

    random.seed(seed)

    BLOCK_SIZE = 4096
    bytes_saved = 0
    with open(path, "wb") as fh:
        while True:
            remaining_bytes = size - bytes_saved
            if remaining_bytes:
                data = random.randbytes(min(remaining_bytes, BLOCK_SIZE))
                bytes_saved += len(data)
                fh.write(data)
            else:
                break

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="destination file path")
    parser.add_argument(
        "size",
        type=parse_size,
        help="size in KiB/MiB/GiB, specify unit with a single suffix letter K/M/G, for example 256k for 256 KiB",
    )
    parser.add_argument("--seed", type=int, default=0, help="Set seed for the random number generator.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing file.")

    args = parser.parse_args()

    create_random_file(args.path, args.size, args.seed, args.overwrite)


if __name__ == "__main__":
    main()
