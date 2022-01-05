#!/usr/bin/env python3
"""
Create torrents via command line!

Copyright (C) 2010-2022 Robert Nitsch
Licensed according to GPL v3.
"""

import argparse
import datetime
import hashlib
import json
import math
import os
import pprint
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Pattern, Set

try:
    from bencodepy import encode as bencode
except ImportError as exc:
    print("ERROR:")
    print("""bencodepy module could not be imported.

Please install the bencodepy module using

    pip install bencode.py

or refer to the documentation on how to install it:
https://py3createtorrent.readthedocs.io/en/latest/""")
    print()
    print()
    print("-" * 40)
    print()
    raise

__all__ = ['calculate_piece_length', 'get_files_in_directory', 'sha1', 'split_path']

# Do not touch anything below this line unless you know what you're doing!

__version__ = '1.0.1'

# Note:
#  Kilobyte = kB  = 1000 Bytes
#  Kibibyte = KiB = 1024 Bytes  << used by py3createtorrent
KIB = 2**10
MIB = KIB * KIB

VERBOSE = False


class Config(object):
    class InvalidConfigError(Exception):
        pass

    def __init__(self) -> None:
        self.path = None  # type: Optional[str]
        self.tracker_abbreviations = {
            'opentrackr': 'udp://tracker.opentrackr.org:1337/announce',
            'coppersurfer': 'udp://tracker.coppersurfer.tk:6969/announce',
            'cyberia': 'udp://tracker.cyberia.is:6969/announce'
        }
        self.advertise = True  # type: Optional[bool]
        self.best_trackers_url = "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_best.txt"  # type: str

    def get_path_to_config_file(self) -> str:
        if self.path is None:
            return os.path.join(os.path.expanduser('~'), '.py3createtorrent.cfg')
        else:
            return self.path

    def load_config(self) -> None:
        """
        @throws json.JSONDecodeError if config file cannot be parsed as JSON
        """
        path = self.get_path_to_config_file()
        printv("Path to config file: ", path)

        if not os.path.isfile(path):
            printv('Config file does not exist')
            return

        with open(path, 'r') as fh:
            data = json.load(fh)

        self.tracker_abbreviations = data.get('tracker_abbreviations', self.tracker_abbreviations)
        self.advertise = data.get('advertise', self.advertise)
        self.best_trackers_url = data.get('best_trackers_url', self.best_trackers_url)

        # Validate the configuration.
        for abbr, replacement in self.tracker_abbreviations.items():
            if not isinstance(abbr, str):
                raise Config.InvalidConfigError("Configuration error: invalid tracker abbreviation: '%s' "
                                                "(must be a string instead)" % abbr)
            if not isinstance(replacement, (str, list)):
                raise Config.InvalidConfigError("Configuration error: invalid tracker abbreviation: '%s' "
                                                "(must be a string or list of strings instead)" % str(replacement))

        if not isinstance(self.best_trackers_url, str):
            raise Config.InvalidConfigError("Configuration error: invalid best trackers url: %s "
                                            "(must be a string)" % self.best_trackers_url)
        if not self.best_trackers_url.startswith("http"):
            raise Config.InvalidConfigError("Configuration error: invalid best trackers url: %s "
                                            "(must be a http/https URL)" % self.best_trackers_url)

        if not isinstance(self.advertise, bool):
            raise Config.InvalidConfigError("Configuration error: invalid value for advertise: %s "
                                            "(must be true/false)" % self.best_trackers_url)


def printv(*args: Any, **kwargs: Any) -> None:
    """If VERBOSE is True, act as an alias for print. Else do nothing."""
    if VERBOSE:
        print(*args, **kwargs)


def sha1(data: bytes) -> bytes:
    """Return the given data's SHA-1 hash (= always 20 bytes)."""
    m = hashlib.sha1()
    m.update(data)
    return m.digest()


def create_single_file_info(file: str, piece_length: int, include_md5: bool = True) -> Dict:
    """
    Return dictionary with the following keys:
      - pieces: concatenated 20-byte-sha1-hashes
      - name:   basename of the file
      - length: size of the file in bytes
      - md5sum: md5sum of the file (unless disabled via include_md5)

    @see:   BitTorrent Metainfo Specification.
    @note:  md5 hashes in torrents are actually optional
    """
    assert os.path.isfile(file), "not a file"

    # Total byte count.
    length = os.path.getsize(file)
    assert length > 0, "empty file"

    # Concatenated 20byte sha1-hashes of all the file's pieces.
    piece_count = int(math.ceil(length / piece_length))
    pieces = bytearray(piece_count * 20)

    if include_md5:
        md5 = hashlib.md5()

    printv("Hashing file... ", end="")

    piece_data = bytearray(piece_length)
    with open(file, "rb") as fh:
        i = 0
        while True:
            # readinto is not recognized by mypy
            # Related: https://github.com/python/typing/issues/659
            #          https://github.com/python/typeshed/issues/2166
            count = fh.readinto(piece_data)  # type: ignore

            if count == piece_length:
                if include_md5:
                    md5.update(piece_data)
                pieces[i * 20:(i + 1) * 20] = sha1(piece_data)
            elif count != 0:
                if include_md5:
                    md5.update(piece_data[:count])
                pieces[i * 20:(i + 1) * 20] = sha1(piece_data[:count])
            else:
                break

            i += 1

    printv("done")

    info = {
        'pieces': bytes(pieces),
        'name': os.path.basename(file),
        'length': length,
    }

    if include_md5:
        info['md5sum'] = md5.hexdigest()

    return info


def create_multi_file_info(directory: str, files: List[str], piece_length: int, include_md5: bool = True) -> Dict:
    """
    Return dictionary with the following keys:
      - pieces: concatenated 20-byte-sha1-hashes
      - name:   basename of the directory (default name of all torrents)
      - files:  a list of dictionaries with the following keys:
        - length: size of the file in bytes
        - md5sum: md5 sum of the file (unless disabled via include_md5)
        - path:   path to the file, relative to the initial directory,
                  given as list.
                  Examples:
                  -> ["dir1", "dir2", "file.ext"]
                  -> ["just_in_the_initial_directory_itself.ext"]

    @see:   BitTorrent Metainfo Specification.
    @note:  md5 hashes in torrents are actually optional
    """
    assert os.path.isdir(directory), "not a directory"

    # Concatenated 20byte sha1-hashes of all the torrent's pieces.
    info_pieces = bytearray()

    #
    info_files = []

    # This bytearray will be used for the calculation of info_pieces.
    # At some point, every file's data will be written into data. Consecutive files will be written into data as a
    # continuous stream, as required by info_pieces' BitTorrent specification.
    data = bytearray()

    for file in files:
        path = os.path.join(directory, file)

        # File's byte count.
        length = 0

        # File's md5sum.
        if include_md5:
            md5 = hashlib.md5()

        printv("Processing file '%s'... " % os.path.relpath(path, directory), end="")

        with open(path, "rb") as fh:
            while True:
                filedata = fh.read(piece_length)

                if len(filedata) == 0:
                    break

                length += len(filedata)

                data += filedata

                if len(data) >= piece_length:
                    info_pieces += sha1(data[:piece_length])
                    data = data[piece_length:]

                if include_md5:
                    md5.update(filedata)

        printv("done")

        # Build the current file's dictionary.
        fdict = {'length': length, 'path': split_path(file)}

        if include_md5:
            fdict['md5sum'] = md5.hexdigest()

        info_files.append(fdict)

    # Don't forget to hash the last piece. (Probably the piece that has not reached the regular piece size.)
    if len(data) > 0:
        info_pieces += sha1(data)

    # Build the final dictionary.
    info = {'pieces': bytes(info_pieces), 'name': os.path.basename(os.path.abspath(directory)), 'files': info_files}

    return info


def get_files_in_directory(directory: str,
                           excluded_paths: Optional[Set[str]] = None,
                           relative_to: Optional[str] = None,
                           excluded_regexps: Optional[Set[Pattern[str]]] = None) -> List[str]:
    """
    Return a list containing the paths to all files in the given directory.

    Paths in excluded_paths are skipped. These should be os.path.normcase()-d.
    Of course, the initial directory cannot be excluded.
    Paths matching any of the regular expressions in excluded_regexps are
    skipped, too. The regexps must be compiled by the caller.
    In both cases, absolute paths are used for matching.

    The paths may be returned relative to a specific directory. By default,
    this is the initial directory itself.

    Please note: Only paths to files are returned!

    @param excluded_regexps: A set of compiled regular expressions.
    """
    # Argument validation:
    if not isinstance(directory, str):
        raise TypeError("directory must be instance of: str")

    if excluded_paths is None:
        excluded_paths = set()
    elif not isinstance(excluded_paths, set):
        raise TypeError("excluded_paths must be instance of: set")

    if relative_to is not None:
        if not isinstance(relative_to, str):
            raise TypeError("relative_to must be instance of: str")

        if not os.path.isdir(relative_to):
            raise ValueError("relative_to: '%s' is not a valid directory" % relative_to)

    if excluded_regexps is None:
        excluded_regexps = set()
    elif not isinstance(excluded_regexps, set):
        raise TypeError("excluded_regexps must be instance of: set")

    # Helper function:
    def _get_files_in_directory(directory: str,
                                files: List[str],
                                excluded_paths: Optional[Set[str]] = None,
                                relative_to: Optional[str] = None,
                                excluded_regexps: Optional[Set[Pattern[str]]] = None,
                                processed_paths: Optional[Set[str]] = None):
        if excluded_paths is None:
            excluded_paths = set()
        if excluded_regexps is None:
            excluded_regexps = set()
        if processed_paths is None:
            processed_paths = set()

        # Improve consistency across platforms.
        # Note:
        listdir = os.listdir(directory)
        listdir.sort(key=str.lower)

        processed_paths.add(os.path.normcase(os.path.realpath(directory)))

        for node in listdir:
            path = os.path.join(directory, node)

            if os.path.normcase(path) in excluded_paths:
                printv("Skipping '%s' due to explicit exclusion." % os.path.relpath(path, relative_to))
                continue

            regexp_match = False
            for regexp in excluded_regexps:
                if regexp.search(path):
                    printv("Skipping '%s' due to pattern exclusion." % os.path.relpath(path, relative_to))
                    regexp_match = True
                    break
            if regexp_match:
                continue

            if os.path.normcase(os.path.realpath(path)) in processed_paths:
                print("Warning: skipping symlink '%s', because it's target "
                      "has already been processed." % path,
                      file=sys.stderr)
                continue
            processed_paths.add(os.path.normcase(os.path.realpath(path)))

            if os.path.isfile(path):
                if relative_to:
                    path = os.path.relpath(path, relative_to)
                files.append(path)
            elif os.path.isdir(path):
                _get_files_in_directory(path,
                                        files,
                                        excluded_paths=excluded_paths,
                                        relative_to=relative_to,
                                        excluded_regexps=excluded_regexps,
                                        processed_paths=processed_paths)
            else:
                assert False, "not a valid node: '%s'" % node

        return files

    # Final preparations:
    directory = os.path.abspath(directory)

    if not relative_to:
        relative_to = directory

    # Now do the main work.
    files = _get_files_in_directory(directory,
                                    list(),
                                    excluded_paths=excluded_paths,
                                    relative_to=relative_to,
                                    excluded_regexps=excluded_regexps)

    return files


def split_path(path: str):
    """
    Return a list containing all of a path's components.

    Paths containing relative components get resolved first.

    >>> split_path("this/./is/a/very/../fucked\\path/file.ext")
    ['this', 'is', 'a', 'fucked', 'path', 'file.ext']
    """
    if not isinstance(path, str):
        raise TypeError("path must be instance of: str")

    parts = []  # type: List[str]

    path = os.path.normpath(path)

    head = path

    while len(head) != 0:
        (head, tail) = os.path.split(head)
        parts.insert(0, tail)

    return parts


def remove_duplicates(old_list: List) -> List:
    """
    Remove any duplicates in old_list, preserving the order of its elements.

    Thus, for all duplicate entries only the first entry is kept in the list.
    """
    new_list = list()
    added_items = set()

    for item in old_list:
        if item in added_items:
            continue

        added_items.add(item)
        new_list.append(item)

    return new_list


def replace_in_list(old_list: List, replacements: Dict) -> List:
    """
    Replace specific items in a list.

    Note that one element may be replaced by multiple new elements. However, this also makes it impossible to
    replace an item with a list.

    Example given:
    >>> replace_in_list(['dont',
                         'replace',
                         'us',
                         'replace me'],
                        {'replace me': ['you',
                                        'are',
                                        'welcome']})
    ['dont', 'replace', 'us', 'you', 'are', 'welcome']
    """
    new_list = list()

    replacements_from = set(replacements.keys())

    for item in old_list:
        if item in replacements_from:
            new_item = replacements[item]

            if isinstance(new_item, list):
                new_list.extend(new_item)
            else:
                new_list.append(new_item)
        else:
            new_list.append(item)

    return new_list


def calculate_piece_length(size: int) -> int:
    """
    Calculate a reasonable piece length for the given torrent size.

    Proceeding:
    1. Start with 256 KIB.
    2. While piece count > 2000: double piece length.
    3. While piece count < 8:    use half the piece length.

    However, enforce these bounds:
    - minimum piece length = 16 KiB.
    - maximum piece length = 16 MiB.
    """
    if not isinstance(size, int):
        raise TypeError("size must be instance of: int")

    if size <= 0:
        raise ValueError("size must be greater than 0 (given: %d)" % size)

    if size < 16 * KIB:
        return 16 * KIB

    piece_length = 256 * KIB

    while size / piece_length > 2000:
        piece_length *= 2

    while size / piece_length < 8:
        piece_length //= 2

    # Ensure that: 16 KIB <= piece_length <= 1 * MIB
    piece_length = max(min(piece_length, 16 * MIB), 16 * KIB)

    return int(piece_length)


def get_best_trackers(count: int, url: str):
    if count < 0:
        raise ValueError("count must be positive")

    if count == 0:
        return []

    with urllib.request.urlopen(url) as f:
        text = f.read().decode('utf-8')

    best = []
    i = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        best.append(line)
        i += 1
        if i == count:
            break

    return best


def main() -> None:
    # Create and configure ArgumentParser.
    parser = argparse.ArgumentParser(
        description="py3createtorrent is a comprehensive command line utility for creating torrents.")

    parser.add_argument("-p",
                        "--piece-length",
                        type=int,
                        action="store",
                        dest="piece_length",
                        default=0,
                        help="piece size in KiB. 0 = automatic selection (default).")

    parser.add_argument("-P",
                        "--private",
                        action="store_true",
                        dest="private",
                        default=False,
                        help="create private torrent")

    parser.add_argument("-c",
                        "--comment",
                        type=str,
                        action="store",
                        dest="comment",
                        default=False,
                        help="include comment")

    parser.add_argument("-s", "--source", type=str, action="store", dest="source", default=False, help="include source")

    parser.add_argument("-f",
                        "--force",
                        action="store_true",
                        dest="force",
                        default=False,
                        help="do not ask anything, just do it")

    parser.add_argument("-v", "--verbose", action="store_true", dest="verbose", default=False, help="verbose mode")

    parser.add_argument("-q",
                        "--quiet",
                        action="store_true",
                        dest="quiet",
                        default=False,
                        help="be quiet, e.g. don't print summary")

    parser.add_argument("-o",
                        "--output",
                        type=str,
                        action="store",
                        dest="output",
                        default=None,
                        metavar="PATH",
                        help="custom output location (directory or complete path). default = current directory.")

    parser.add_argument("-e",
                        "--exclude",
                        type=str,
                        action="append",
                        dest="exclude",
                        default=[],
                        metavar="PATH",
                        help="exclude path (can be repeated)")

    parser.add_argument("--exclude-pattern",
                        type=str,
                        action="append",
                        dest="exclude_pattern",
                        default=[],
                        metavar="REGEXP",
                        help="exclude paths matching the regular expression (can be repeated)")

    parser.add_argument("--exclude-pattern-ci",
                        type=str,
                        action="append",
                        dest="exclude_pattern_ci",
                        default=[],
                        metavar="REGEXP",
                        help="exclude paths matching the case-insensitive regular expression (can be repeated)")

    parser.add_argument("-d",
                        "--date",
                        type=int,
                        action="store",
                        dest="date",
                        default=-1,
                        metavar="TIMESTAMP",
                        help="set creation date (unix timestamp). -1 = now (default). -2 = disable.")

    parser.add_argument("-n",
                        "--name",
                        type=str,
                        action="store",
                        dest="name",
                        default=None,
                        help="use this file (or directory) name instead of the real one")

    parser.add_argument("--md5",
                        action="store_true",
                        dest="include_md5",
                        default=False,
                        help="include MD5 hashes in torrent file")

    parser.add_argument("--config",
                        type=str,
                        action="store",
                        help="use another config file instead of the default one from the home directory")

    parser.add_argument("-t",
                        "--tracker",
                        metavar="TRACKER_URL",
                        action="append",
                        dest="trackers",
                        default=[],
                        help="tracker to use for the torrent")
    parser.add_argument("--node",
                        metavar="HOST,PORT",
                        action="append",
                        dest="nodes",
                        default=[],
                        help="DHT bootstrap node to use for the torrent")
    parser.add_argument("--webseed",
                        metavar="WEBSEED_URL",
                        action="append",
                        dest="webseeds",
                        default=[],
                        help="webseed URL for the torrent")

    parser.add_argument("path", help="file or folder for which to create a torrent")

    args = parser.parse_args()

    global VERBOSE
    VERBOSE = args.verbose

    config = Config()
    if args.config:
        if not os.path.isfile(args.config):
            parser.error("The config file at '%s' does not exist" % args.config)
        config.path = args.config

    try:
        config.load_config()
    except json.JSONDecodeError as exc:
        print("Could not parse config file at '%s'" % config.get_path_to_config_file(), file=sys.stderr)
        print(exc, file=sys.stderr)
        sys.exit(1)
    except Config.InvalidConfigError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    printv('Config / Tracker abbreviations:\n' + pprint.pformat(config.tracker_abbreviations))
    printv('Config / Advertise:         ' + str(config.advertise))
    printv('Config / Best trackers URL: ' + config.best_trackers_url)

    # Ask the user if he really wants to use uncommon piece lengths.
    # (Unless the force option has been set.)
    if not args.force and 0 < args.piece_length < 16:
        if "yes" != input("It is strongly recommended to use a piece length greater or equal than 16 KiB! Do you "
                          "really want to continue? yes/no: "):
            parser.error("Aborted.")

    if not args.force and args.piece_length > 16384:
        if "yes" != input(
                "It is strongly recommended to use a maximum piece length of 16384 KiB (16 MiB)! Do you really "
                "want to continue? yes/no: "):
            parser.error("Aborted.")

    if not args.force and args.piece_length % 16 != 0:
        if "yes" != input(
                "It is strongly recommended to use a piece length that is a multiple of 16 KiB! Do you really "
                "want to continue? yes/no: "):
            parser.error("Aborted.")

    # Verbose and quiet options may not be used together.
    if args.verbose and args.quiet:
        parser.error("Being verbose and quiet exclude each other.")

    # ##########################################
    # CALCULATE/SET THE FOLLOWING METAINFO DATA:
    # - info
    #   - pieces (concatenated 20 byte sha1 hashes of all the data)
    #   - files (if multiple files)
    #   - length and md5sum (if single file)
    #   - name (may be overwritten in the next section by the --name option)

    input_path = args.path  # type: str
    trackers = args.trackers  # type: List[str]

    # Validate the given path.
    if not os.path.isfile(input_path) and not os.path.isdir(input_path):
        parser.error("'%s' neither is a file nor a directory." % input_path)

    # Evaluate / apply the tracker abbreviations.
    trackers = replace_in_list(trackers, config.tracker_abbreviations)

    # Remove duplicate trackers.
    trackers = remove_duplicates(trackers)

    # Validate tracker URLs.
    invalid_trackers = False
    best_shortcut_present = False
    regexp = re.compile(r"^(http|https|udp)://", re.I)
    regexp_best = re.compile(r"best([0-9]+)", re.I)
    for t in trackers:
        m = regexp_best.match(t)
        if m:
            best_shortcut_present = True
        if not regexp.search(t) and not m:
            print("Warning: Not a valid tracker URL: %s" % t, file=sys.stderr)
            invalid_trackers = True

    if invalid_trackers and not args.force:
        if "yes" != input("Some tracker URLs are invalid. Continue? yes/no: "):
            parser.error("Aborted.")

    # Handle best[0-9] shortcut.
    if best_shortcut_present:
        new_trackers = []
        for t in trackers:
            m = regexp_best.match(t)
            if m:
                try:
                    new_trackers.extend(get_best_trackers(int(m.group(1)), config.best_trackers_url))
                except urllib.error.URLError as e:
                    print("Error: Could not download best trackers from '%s'. Reason: %s" %
                          (config.best_trackers_url, e),
                          file=sys.stderr)
                    sys.exit(1)
            else:
                new_trackers.append(t)
        trackers = new_trackers

    # Disallow DHT bootstrap nodes for private torrents.
    if args.nodes and args.private:
        parser.error(
            "DHT bootstrap nodes cannot be specified for a private torrent. Private torrents do not support DHT.")

    # Validate DHT bootstrap nodes.
    parsed_nodes = list()
    invalid_nodes = False
    for n in args.nodes:
        splitted = n.split(",")
        if len(splitted) != 2:
            print("Invalid format for DHT bootstrap node '%s'. Please use the format 'host,port'." % n, file=sys.stderr)
            invalid_nodes = True
            continue

        host, port = splitted
        if not port.isdigit():
            print("Invalid port number for DHT bootstrap node '%s'. Ports must be numeric." % n, file=sys.stderr)
            invalid_nodes = True

        parsed_nodes.append([host, int(port)])

    if invalid_nodes and not args.force:
        if "yes" != input("Some DHT bootstrap nodes are invalid. Continue? yes/no: "):
            parser.error("Aborted.")

    # Parse and validate excluded paths.
    excluded_paths = set([os.path.normcase(os.path.abspath(path)) for path in args.exclude])

    # Parse exclude patterns.
    excluded_regexps = set(re.compile(regexp) for regexp in args.exclude_pattern)
    excluded_regexps |= set(re.compile(regexp, re.IGNORECASE) for regexp in args.exclude_pattern_ci)

    # Warn the user if he attempts to exclude any paths when creating a torrent for a single file (makes no sense).
    if os.path.isfile(input_path) and (len(excluded_paths) > 0 or len(excluded_regexps) > 0):
        print("Warning: Excluding paths is not possible when creating a torrent for a single file.", file=sys.stderr)

    # Warn the user if he attempts to exclude a specific path, that does not even exist.
    for path in excluded_paths:
        if not os.path.exists(path):
            print("Warning: You're excluding a path that does not exist: '%s'" % path, file=sys.stderr)

    # Get the torrent's files and / or calculate its size.
    if os.path.isfile(input_path):
        torrent_size = os.path.getsize(input_path)
    else:
        torrent_files = get_files_in_directory(input_path,
                                               excluded_paths=excluded_paths,
                                               excluded_regexps=excluded_regexps)
        torrent_size = sum([os.path.getsize(os.path.join(input_path, file)) for file in torrent_files])

    # Torrents for 0 byte data can't be created.
    if torrent_size == 0:
        print("Error: Can't create torrent for 0 byte data.", file=sys.stderr)
        print("Check your files and exclusions!", file=sys.stderr)
        sys.exit(1)

    # Calculate or parse the piece size.
    if args.piece_length == 0:
        piece_length = calculate_piece_length(torrent_size)
    elif args.piece_length > 0:
        piece_length = args.piece_length * KIB
    else:
        parser.error("Invalid piece size: '%d'" % args.piece_length)

    # Do the main work now.
    # -> prepare the metainfo dictionary.
    if os.path.isfile(input_path):
        info = create_single_file_info(input_path, piece_length, args.include_md5)
    else:
        info = create_multi_file_info(input_path, torrent_files, piece_length, args.include_md5)

    assert len(info['pieces']) % 20 == 0, "len(pieces) not a multiple of 20"

    # ###########################
    # FINISH METAINFO DICTIONARY:
    # - info
    #   - piece length
    #   - name (eventually overwrite)
    #   - private
    # - announce (if at least one tracker was specified)
    # - announce-list (if multiple trackers were specified)
    # - nodes (if at least one DHT bootstrap node was specified)
    # - creation date (may be disabled as well)
    # - created by
    # - comment (may be disabled as well)

    # Finish sub-dict "info".
    info['piece length'] = piece_length

    if args.private:
        info['private'] = 1

    # Re-use the name regex for source parameter.
    if args.source:
        args.source = args.source.strip()

        regexp = re.compile(r"^[A-Z0-9_\-., ]+$", re.I)

        if not regexp.match(args.source):
            parser.error("Invalid source: '%s'. Allowed chars: A_Z, a-z, 0-9, any of {.,_-} plus spaces." % args.source)

        info['source'] = args.source

    # Construct outer metainfo dict, which contains the torrent's whole information.
    metainfo = {'info': info}  # type: Dict[str, Any]
    if trackers:
        metainfo['announce'] = trackers[0]

    # Make "announce-list" field, if there are multiple trackers.
    if len(trackers) > 1:
        metainfo['announce-list'] = [[tracker] for tracker in trackers]

    # Set DHT bootstrap nodes.
    if parsed_nodes:
        metainfo['nodes'] = parsed_nodes

    # Set webseeds (url-list).
    if args.webseeds:
        metainfo['url-list'] = args.webseeds

    # Set "creation date".
    # The user may specify a custom creation date. He may also decide not to include the creation date field at all.
    if args.date == -1:
        # use current time
        metainfo['creation date'] = int(time.time())
    elif args.date >= 0:
        # use specified timestamp directly
        metainfo['creation date'] = args.date
    elif args.date < -2:
        parser.error("Invalid date: Negative timestamp values are not possible (except for -1 to use current date "
                     "automatically or -2 to disable storing a creation date altogether).")

    # Add the "created by" field.
    metainfo['created by'] = 'py3createtorrent v%s' % __version__

    # Add user's comment or advertise py3createtorrent (unless this behaviour has been disabled by the user).
    # The user may also decide not to include the comment field at all by specifying an empty comment.
    if isinstance(args.comment, str):
        if len(args.comment) > 0:
            metainfo['comment'] = args.comment
    elif config.advertise:
        metainfo['comment'] = "created with " + metainfo['created by']

    # Add the name field.
    # By default this is the name of directory or file the torrent is being created for.
    if args.name:
        args.name = args.name.strip()

        regexp = re.compile(r"^[A-Z0-9_\-., ()]+$", re.I)

        if not regexp.match(args.name):
            parser.error("Invalid name: '%s'. Allowed chars: A_Z, a-z, 0-9, any of {.,_-()} plus spaces." % args.name)

        metainfo['info']['name'] = args.name

    # ###################################################
    # BENCODE METAINFO DICTIONARY AND WRITE TORRENT FILE:
    # - take into consideration the --output option
    # - properly handle KeyboardInterrupts while writing the file

    # Respect the custom output location.
    if not args.output:
        # Use current directory.
        output_path = metainfo['info']['name'] + ".torrent"

    else:
        # Use the directory or filename specified by the user.
        args.output = os.path.abspath(args.output)

        # The user specified an output directory:
        if os.path.isdir(args.output):
            output_path = os.path.join(args.output, metainfo['info']['name'] + ".torrent")
            if os.path.isfile(output_path):
                if not args.force and os.path.exists(output_path):
                    if "yes" != input("'%s' does already exist. Overwrite? yes/no: " % output_path):
                        parser.error("Aborted.")

        # The user specified a filename:
        else:
            # Is there already a file with this path? -> overwrite?!
            if os.path.isfile(args.output):
                if not args.force and os.path.exists(args.output):
                    if "yes" != input("'%s' does already exist. Overwrite? yes/no: " % args.output):
                        parser.error("Aborted.")

            output_path = args.output

    # Actually write the torrent file now.
    try:
        with open(output_path, "wb") as fh:
            fh.write(bencode(metainfo))
    except IOError as exc:
        print("IOError: " + str(exc), file=sys.stderr)
        print("Could not write the torrent file. Check torrent name and your privileges.", file=sys.stderr)
        print("Absolute output path: '%s'" % os.path.abspath(output_path), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        # Properly handle KeyboardInterrupts.
        # todo: open()'s context manager may already do this on his own?
        if os.path.exists(output_path):
            os.remove(output_path)

    # #########################
    # PREPARE AND PRINT SUMMARY
    # - but check quiet option

    # If the quiet option has been set, we're already finished here, because we don't print a summary in this case.
    if args.quiet:
        sys.exit(0)

    # Print summary!
    print("Successfully created torrent:")

    # Create the list of backup trackers.
    backup_trackers = ""
    if 'announce-list' in metainfo:
        _backup_trackers = metainfo['announce-list'][1:]
        _backup_trackers.sort(key=lambda x: x[0].lower())

        for tracker in _backup_trackers:
            backup_trackers += "    " + tracker[0] + "\n"
        backup_trackers = backup_trackers.rstrip()
    else:
        backup_trackers = "    (none)"

    # Calculate piece count.
    piece_count = math.ceil(torrent_size / metainfo['info']['piece length'])

    # Make torrent size human readable.
    if torrent_size > 10 * MIB:
        size = "%.2f MiB" % (torrent_size / MIB)
    else:
        size = "%d KiB" % (torrent_size / KIB)

    # Make creation date human readable (ISO format).
    if 'creation date' in metainfo:
        creation_date = datetime.datetime.fromtimestamp(metainfo['creation \
date']).isoformat(' ')
    else:
        creation_date = "(none)"

    # Now actually print the summary table.
    print("  Name:                %s\n"
          "  Size:                %s\n"
          "  Pieces:              %d x %d KiB\n"
          "  Comment:             %s\n"
          "  Private:             %s\n"
          "  Creation date:       %s\n"
          "  DHT bootstrap nodes: %s\n"
          "  Webseeds:            %s\n"
          "  Primary tracker:     %s\n"
          "  Backup trackers:\n"
          "%s" %
          (metainfo['info']['name'], size, piece_count, piece_length / KIB,
           metainfo['comment'] if 'comment' in metainfo else "(none)", "yes" if args.private else "no", creation_date,
           metainfo['nodes'] if 'nodes' in metainfo else "(none)", metainfo['url-list'] if 'url-list' in metainfo else
           "(none)", metainfo['announce'] if 'announce' in metainfo else "(none)", backup_trackers))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
