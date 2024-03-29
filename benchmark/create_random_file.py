"""
Script to create files of given size with pseudo-random content.
"""
import argparse
import os
import random
import sys


def parse_size(size):
    letter_to_unit = {"K": 2**10, "M": 2**20, "G": 2**30}

    error_message = ("must be a number ending with a single letter to "
                     "indicate the unit type K, M or G - for example, use 256k to specify 256 KiB")

    letter = size[-1]
    if letter.isdigit():
        raise argparse.ArgumentTypeError(error_message)

    number = size[:-1]
    if not number.isdigit():
        raise argparse.ArgumentTypeError(error_message)

    return letter_to_unit[letter.upper()] * int(number)


def create_random_file(dst, size):
    BLOCK_SIZE = 4096
    bytes_saved = 0
    with open(dst, "wb") as fh:
        while True:
            remaining_bytes = size - bytes_saved
            if remaining_bytes:
                data = random.randbytes(min(remaining_bytes, BLOCK_SIZE))
                bytes_saved += len(data)
                fh.write(data)
            else:
                break


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

    if os.path.isfile(args.path) and not args.overwrite:
        if os.path.getsize(args.path) != args.size:
            print(
                "ERROR: Destination file already exists BUT DOES NOT HAVE THE CORRECT SIZE",
                file=sys.stderr,
            )
        else:
            print(
                "WARNING: Destination file already exists (already has the requested size)",
                file=sys.stderr,
            )
        print("Not doing anything. Use --overwrite option to force overwriting the existing file.")
        sys.exit(1)

    random.seed(args.seed)
    create_random_file(args.path, args.size)


if __name__ == "__main__":
    main()
