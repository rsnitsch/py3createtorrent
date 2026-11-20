#!/usr/bin/env python3
"""
Script to generate a specified number of files with pseudo-random names/contents in
a given directory. The size of each file will be randomly (uniformly) chosen from a
user-specified range.
"""

import argparse
import logging
import random
from pathlib import Path

import cachedir_tag
from create_random_file import create_random_file, parse_size
from faker import Faker

logger = logging.getLogger(__name__)


def create_random_folder(
    path: Path,
    number_of_files: int,
    min_file_size: int,
    max_file_size: int,
    seed: int = 0,
    create_cachedir_tag: bool = True,
):
    if min_file_size > max_file_size:
        raise ValueError("min_file_size is larger than max_file_size")

    random.seed(seed)
    fake = Faker()
    Faker.seed(seed)

    path.mkdir(parents=True, exist_ok=True)
    if create_cachedir_tag:
        cachedir_tag.tag(path)

    generated_filenames: set[str] = set()
    filename = fake.file_name()
    for _ in range(number_of_files):
        generated_filenames.add(filename)
        size = random.randint(min_file_size, max_file_size)
        logger.debug("Creating random file: % 20s of size: % 10d bytes...", filename, size)
        create_random_file(path.joinpath(filename), size)

        while filename in generated_filenames:
            filename = fake.file_name()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, help="destination folder path")
    parser.add_argument("number_of_files", type=int, help="Number of files to generate")
    parser.add_argument(
        "min_file_size",
        type=parse_size,
        help="minimum file size in KiB/MiB/GiB, specify unit with a single suffix letter K/M/G, for example 256k for 256 KiB",
    )
    parser.add_argument("max_file_size", type=parse_size, help="maximum file size")
    parser.add_argument("--seed", type=int, default=0, help="Set seed for the random number generator.")
    parser.add_argument(
        "--no-cachedir-tag",
        action="store_true",
        help="Do not generate CACHEDIR.TAG file",
    )

    args = parser.parse_args()

    if args.min_file_size > args.max_file_size:
        parser.error("min_file_size must be smaller or equal than max_file_size")

    create_random_folder(
        args.path, args.number_of_files, args.min_file_size, args.max_file_size, args.seed, not args.no_cachedir_tag
    )


if __name__ == "__main__":
    main()
