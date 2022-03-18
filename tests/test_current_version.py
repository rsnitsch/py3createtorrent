"""
Test the local src/py3createtorrent.py against the reference torrent files in tests/referencedata.
"""
import argparse
import os
import subprocess
import sys


def get_file_contents(path):
    with open(path, "rb") as fh:
        return fh.read()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-threads", action="store_true", help="Enable testing of various numbers of threads.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output for debugging purposes.")
    args = parser.parse_args()

    if not os.path.isfile(os.path.join("src", "py3createtorrent.py")):
        print("This script must be executed from the projects top-level directory.", file=sys.stderr)
        return 1

    threads = [1]
    if args.test_threads:
        threads = range(1, 4)
    else:
        print("Testing without --threads option...")

    piece_sizes = [16, 128, 1024, 8192]
    targets = ["random_folder", "random_file.dat"]
    for t in threads:
        if args.test_threads:
            print("Testing with --threads %d:" % t)
        for target in targets:
            target_path = os.path.join("tests", "testdata", target)
            if "." in target:
                target = target.split(".")[0]

            for p in piece_sizes:
                torrent_file = os.path.join("tests", "testdata", "%s_currentversion_p%d.torrent" % (target, p))
                if os.path.isfile(torrent_file):
                    os.remove(torrent_file)

                cmd = r'python src\py3createtorrent.py --no-created-by -c "" --date -2 %s -p %d -o %s' % (
                    target_path, p, torrent_file)
                if args.test_threads:
                    cmd += " --threads %d" % t
                if args.verbose:
                    print("cmd: ", cmd)
                cp = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL)

                reference_file = os.path.join("tests", "referencedata", "%s_py3createtorrent_p%d.torrent" % (target, p))

                if args.verbose:
                    print("Torrent file:   %s" % torrent_file)
                    print("Reference file: %s" % reference_file)
                actual_bytes = get_file_contents(torrent_file)
                expected_bytes = get_file_contents(reference_file)

                if actual_bytes == expected_bytes:
                    print("Torrent files for % 15s with piece size % 5d are matching: YES" % (target, p))
                else:
                    print("Torrent files for % 15s with piece size % 5d are matching: NO" % (target, p))

    return 0


if __name__ == '__main__':
    sys.exit(main())
