"""
Script to generate a specified number of files with pseudo-random names/contents in
a given directory. The size of each file will be randomly (uniformly) chosen from a
user-specified range.
"""
import argparse
import random
from pathlib import Path

from create_random_file import parse_size, create_random_file
from faker import Faker


def create_cache_dir_tag(path):
    path = Path(path)
    if path.is_dir():
        path = path.joinpath("CACHEDIR.TAG")
    elif not path.name == "CACHEDIR.TAG":
        raise ValueError("Full file path was specified, but file name is not CACHEDIR.TAG")

    with open(path, "w") as fh:
        fh.write("Signature: 8a477f597d28d172789f06886806bc55\n")
        fh.write("# This file instructs backup applications to ignore this directory.\n")
        fh.write("# For more information see https://www.brynosaurus.com/cachedir/\n")

    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, help="destination folder path")
    parser.add_argument("number_of_files", type=int, help="Number of files to generate")
    parser.add_argument(
        "min_file_size",
        type=parse_size,
        help=
        "minimum file size in KiB/MiB/GiB, specify unit with a single suffix letter K/M/G, for example 256k for 256 KiB"
    )
    parser.add_argument("max_file_size", type=parse_size, help="maximum file size")
    parser.add_argument("--seed", type=int, default=0, help="Set seed for the random number generator.")
    parser.add_argument("--no-cachedir-tag", action="store_true", help="Do not generate CACHEDIR.TAG file")

    args = parser.parse_args()

    if args.min_file_size > args.max_file_size:
        parser.error("min_file_size must be smaller or equal than max_file_size")

    random.seed(args.seed)
    fake = Faker()
    Faker.seed(args.seed)

    args.path.mkdir(parents=True, exist_ok=True)
    if not args.no_cachedir_tag:
        p = create_cache_dir_tag(args.path)
        print("Saved cachedir tag at: %s" % p)

    for i in range(args.number_of_files):
        filename = fake.file_name()
        size = random.randint(args.min_file_size, args.max_file_size)
        print("Creating random file: % 20s of size: % 10d bytes..." % (filename, size))
        create_random_file(args.path.joinpath(filename), size)


if __name__ == '__main__':
    main()
