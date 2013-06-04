#!/usr/bin/env python3
"""
Create torrents via command line!

Copyright (C) 2010-2013 Robert Nitsch
Licensed according to GPL v3.
"""

import datetime
import hashlib
import math
import optparse
import os
import re
import sys
import time

from py3bencode import bencode

__all__ = ['calculate_piece_length',
           'get_files_in_directory',
           'sha1_20',
           'split_path']

# #############
# CONFIGURATION

# configure your tracker abbreviations here
TRACKER_ABBR = {'openbt':       'udp://tracker.openbittorrent.com:80',
                'publicbt':     'udp://tracker.publicbt.com:80'}

# whether or not py3createtorrent is allowed to advertise itself
# through the torrents' comment fields
ADVERTISE = True

# /CONFIGURATION
# ##############

# do not touch anything below this line unless you know what you're doing!


VERSION =   '0.9.5'

# Note:
#  Kilobyte = kB  = 1000 Bytes
#  Kibibyte = KiB = 1024 Bytes  << used by py3createtorrent
KIB = 2**10
MIB = KIB * KIB


VERBOSE = False
def printv(*args, **kwargs):
    """If VERBOSE is True, act as an alias for print. Else do nothing."""
    if VERBOSE:
        print(*args, **kwargs)

def sha1_20(data):
    """Return the first 20 bytes of the given data's SHA-1 hash."""
    m = hashlib.sha1()
    m.update(data)
    return m.digest()[:20]

def create_single_file_info(file, piece_length, include_md5=True):
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
    length = 0

    # Concatenated 20byte sha1-hashes of all the file's pieces.
    pieces = bytearray()

    md5 = hashlib.md5() if include_md5 else None

    printv("Hashing file... ", end="")

    with open(file, "rb") as fh:
        while True:
            piece_data = fh.read(piece_length)

            _len = len(piece_data)
            if _len == 0:
                break

            if include_md5:
                md5.update(piece_data)

            length += _len

            pieces += sha1_20(piece_data)

    printv("done")

    assert length > 0, "empty file"

    info =  {
            'pieces': pieces,
            'name':   os.path.basename(file),
            'length': length,
            
            }

    if include_md5:
        info['md5sum'] = md5.hexdigest()

    return info

def create_multi_file_info(directory,
                           files,
                           piece_length,
                           include_md5=True):
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
    # At some point, every file's data will be written into data. Consecutive
    # files will be written into data as a continuous stream, as required
    # by info_pieces' BitTorrent specification.
    data = bytearray()

    for file in files:
        path = os.path.join(directory, file)

        # File's byte count.
        length = 0

        # File's md5sum.
        md5 = hashlib.md5() if include_md5 else None

        printv("Processing file '%s'... " % os.path.relpath(path, directory),
               end="")

        with open(path, "rb") as fh:
            while True:
                filedata = fh.read(piece_length)

                if len(filedata) == 0:
                    break

                length += len(filedata)

                data += filedata

                if len(data) >= piece_length:
                    info_pieces  +=  sha1_20(data[:piece_length])
                    data          =  data[piece_length:]

                if include_md5:
                    md5.update(filedata)

        printv("done")

        # Build the current file's dictionary.
        fdict = {
                'length': length,
                'path':   split_path(file)
                }

        if include_md5:
            fdict['md5sum'] = md5.hexdigest()

        info_files.append(fdict)

    # Don't forget to hash the last piece.
    # (Probably the piece that has not reached the regular piece size.)
    if len(data) > 0:
        info_pieces += sha1_20(data)

    # Build the final dictionary.
    info = {
           'pieces': info_pieces,
           'name':   os.path.basename(directory.strip("/\\")),
           'files':  info_files
           }

    return info

def get_files_in_directory(directory,
                           excluded_paths=set(),
                           relative_to=None,
                           excluded_regexps=set()):
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
    
    @param excluded_regexps: A set or frozenset of compiled regular expressions.
    """
    # Argument validation:
    if not isinstance(directory, str):
        raise TypeError("directory must be instance of: str")

    if not isinstance(excluded_paths, (set, frozenset)):
        raise TypeError("excluded_paths must be instance of: set or frozenset")

    if relative_to is not None:
        if not isinstance(relative_to, str):
            raise TypeError("relative_to must be instance of: str")

        if not os.path.isdir(relative_to):
            raise ValueError("relative_to: '%s' is not a valid directory" %
                             (relative_to))

    if not isinstance(excluded_regexps, (set, frozenset)):
        raise TypeError("excluded_regexps must be instance of: set or frozenset")

    # Helper function:
    def _get_files_in_directory(directory,
                                files,
                                excluded_paths=set(),
                                relative_to=None,
                                excluded_regexps=set(),
                                processed_paths=set()):
        # Improve consistency across platforms.
        # Note:
        listdir = os.listdir(directory)
        listdir.sort(key=str.lower)

        processed_paths.add(os.path.normcase(os.path.realpath(directory)))

        for node in listdir:
            path = os.path.join(directory, node)

            if os.path.normcase(path) in excluded_paths:
                printv("Skipping '%s' due to explicit exclusion." %
                       os.path.relpath(path, relative_to))
                continue

            regexp_match = False
            for regexp in excluded_regexps:
                if regexp.search(path):
                    printv("Skipping '%s' due to pattern exclusion." %
                           os.path.relpath(path, relative_to))
                    regexp_match = True
                    break
            if regexp_match:
                continue

            if os.path.normcase(os.path.realpath(path)) in processed_paths:
                print("Warning: skipping symlink '%s', because it's target "
                      "has already been processed." % path, file=sys.stderr)
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

def split_path(path):
    """
    Return a list containing all of a path's components.

    Paths containing relative components get resolved first.

    >>> split_path("this/./is/a/very/../fucked\\path/file.ext")
    ['this', 'is', 'a', 'fucked', 'path', 'file.ext']
    """
    if not isinstance(path, str):
        raise TypeError("path must be instance of: str")

    parts = []

    path = os.path.normpath(path)

    head = path

    while len(head) != 0:
        (head, tail) = os.path.split(head)
        parts.insert(0, tail)

    return parts

def remove_duplicates(old_list):
    """
    Remove any duplicates in old_list, preserving the order of its
    elements.

    Thus, for all duplicate entries only the first entry is kept in
    the list.
    """
    new_list = list()
    added_items = set()

    for item in old_list:
        if item in added_items:
            continue

        added_items.add(item)
        new_list.append(item)

    return new_list

def replace_in_list(old_list, replacements):
    """
    Replace specific items in a list.

    Note that one element may be replaced by multiple new elements.
    However, this also makes it impossible to replace an item with a
    list.

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

def calculate_piece_length(size):
    """
    Calculate a reasonable piece length for the given torrent size.

    Proceeding:
    1. Start with 256 KIB.
    2. While piece count > 2000: double piece length.
    3. While piece count < 8:    use half the piece length.

    However, enforce these bounds:
    - minimum piece length = 16 KiB.
    - maximum piece length =  1 MiB.
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
        piece_length /= 2

    # Ensure that: 16 KIB <= piece_length <= 1 * MIB
    piece_length = max(min(piece_length, 1 * MIB), 16 * KIB)

    return int(piece_length)

def main(argv):
    # Validate the configuration.
    for abbr, replacement in TRACKER_ABBR.items():
        if not isinstance(abbr, str):
            print("Configuration error: invalid tracker abbrevation: '%s' "
                  "(must be a string instead)" % abbr,
                  file=sys.stderr)
            return 1
        if not isinstance(replacement, (str, list)):
            print("Configuration error: invalid tracker abbreviation: '%s' "
                  "(must be a string or list of strings instead)" % str(replacement),
                  file=sys.stderr)
            return 1

    # Create OptionParser.
    kwargs =  {
              'usage':
              "%prog [options] <file-or-directory> <main-tracker-url> "
              "[<backup-tracker-url> ...]",

              'version':
              "%%prog v%s" % VERSION,

              'description':
              "py3createtorrent is a comprehensive command line utility for "
              "creating torrents."
              }

    parser = optparse.OptionParser(**kwargs)

    # Add options to the OptionParser.
    # Note: Commonly used options are added first.
    parser.add_option("-p", "--piece-length", type="int", action="store",
                      dest="piece_length", default=0,
                      help="piece size in KiB. 0 = automatic selection (default).")

    parser.add_option("-P", "--private", action="store_true",
                      dest="private", default=False,
                      help="create private torrent")

    parser.add_option("-c", "--comment", type="string", action="store",
                      dest="comment", default=False,
                      help="include comment")

    parser.add_option("-f", "--force", action="store_true",
                      dest="force", default=False,
                      help="dont ask anything, just do it")

    parser.add_option("-v", "--verbose", action="store_true",
                      dest="verbose", default=False,
                      help="verbose mode")

    parser.add_option("-q", "--quiet", action="store_true",
                      dest="quiet", default=False,
                      help="be quiet, e.g. don't print summary")

    parser.add_option("-o", "--output", type="string", action="store",
                      dest="output", default=None, metavar="PATH",
                      help="custom output location (directory or complete "
                           "path). default = current directory.")

    parser.add_option("-e", "--exclude", type="string", action="append",
                      dest="exclude", default=[], metavar="PATH",
                      help="exclude path (can be repeated)")

    parser.add_option("--exclude-pattern", type="string", action="append",
                      dest="exclude_pattern", default=[], metavar="REGEXP",
                      help="exclude paths matching the regular expression "
                           "(can be repeated)")
                           
    parser.add_option("--exclude-pattern-ci", type="string", action="append",
                      dest="exclude_pattern_ci", default=[], metavar="REGEXP",
                      help="exclude paths matching the case-insensitive regular "
                           "expression (can be repeated)")

    parser.add_option("-d", "--date", type="int", action="store",
                      dest="date", default=-1, metavar="TIMESTAMP",
                      help="set creation date (unix timestamp). -1 = now "
                           "(default). -2 = disable.")

    parser.add_option("-n", "--name", type="string", action="store",
                      dest="name", default=None,
                      help="use this file (or directory) name instead of the "
                           "real one")

    parser.add_option("--md5", action="store_true",
                      dest="include_md5", default=False,
                      help="include MD5 hashes in torrent file")

    (options, args) = parser.parse_args(args = argv[1:])

    # Positional arguments must have been provided:
    # -> file / directory plus at least one tracker.
    if len(args) < 2:
        parser.error("You must specify a valid path and at least one tracker.")

    # Ask the user if he really wants to use uncommon piece lengths.
    # (Unless the force option has been set.)
    if not options.force and 0 < options.piece_length < 16:
        if "yes" != input("It is strongly recommended to use a piece length "
                          "greater or equal than 16 KiB! Do you really want "
                          "to continue? yes/no: "):
            parser.error("Aborted.")

    if not options.force and options.piece_length > 1024:
        if "yes" != input("It is strongly recommended to use a maximum piece "
                          "length of 1024 KiB! Do you really want to "
                          "continue? yes/no: "):
            parser.error("Aborted.")

    # Verbose and quiet options may not be used together.
    if options.verbose and options.quiet:
        parser.error("Being verbose and quiet exclude each other.")

    global VERBOSE
    VERBOSE = options.verbose

    # ##########################################
    # CALCULATE/SET THE FOLLOWING METAINFO DATA:
    # - info
    #   - pieces (concatenated 20 byte sha1 hashes of all the data)
    #   - files (if multiple files)
    #   - length and md5sum (if single file)
    #   - name (may be overwritten in the next section by the --name option)

    node     = os.path.abspath(args[0])
    trackers = args[1:]

    # Validate the given path.
    if not os.path.isfile(node) and not os.path.isdir(node):
        parser.error("'%s' neither is a file nor a directory." % node)

    # Evaluate / apply the tracker abbreviations.
    trackers = replace_in_list(trackers, TRACKER_ABBR)

    # Remove duplicate trackers.
    trackers = remove_duplicates(trackers)

    # Validate tracker URLs.
    invalid_trackers = False
    regexp = re.compile(r"^(http|https|udp)://", re.I)
    for t in trackers:
        if not regexp.search(t):
            print("Warning: Not a valid tracker URL: %s" % t, file=sys.stderr)
            invalid_trackers = True

    if invalid_trackers and not options.force:
        if "yes" != input("Some tracker URLs are invalid. Continue? yes/no: "):
            parser.error("Aborted.")

    # Parse and validate excluded paths.
    excluded_paths = frozenset([os.path.normcase(os.path.abspath(path)) \
                                for path in options.exclude])

    # Parse exclude patterns.
    excluded_regexps = set(re.compile(regexp) for regexp in options.exclude_pattern)
    excluded_regexps |= set(re.compile(regexp, re.IGNORECASE)
                            for regexp in options.exclude_pattern_ci)

    # Warn the user if he attempts to exclude any paths when creating
    # a torrent for a single file (makes no sense).
    if os.path.isfile(node) and (len(excluded_paths) > 0 or \
       len(excluded_regexps) > 0):
        print("Warning: Excluding paths is not possible when creating a "
              "torrent for a single file.", file=sys.stderr)

    # Warn the user if he attempts to exclude a specific path, that does not
    # even exist.
    for path in excluded_paths:
        if not os.path.exists(path):
            print("Warning: You're excluding a path that does not exist: '%s'"
                  % path, file=sys.stderr)

    # Get the torrent's files and / or calculate its size.
    if os.path.isfile(node):
        torrent_size = os.path.getsize(node)
    else:
        torrent_files = get_files_in_directory(node,
                                         excluded_paths=excluded_paths,
                                         excluded_regexps=excluded_regexps)
        torrent_size = sum([os.path.getsize(os.path.join(node, file))
                            for file in torrent_files])

    # Torrents for 0 byte data can't be created.
    if torrent_size == 0:
        print("Error: Can't create torrent for 0 byte data.", file=sys.stderr)
        print("Check your files and exclusions!", file=sys.stderr)
        return 1

    # Calculate or parse the piece size.
    if options.piece_length == 0:
        piece_length = calculate_piece_length(torrent_size)
    elif options.piece_length > 0:
        piece_length = options.piece_length * KIB
    else:
        parser.error("Invalid piece size: '%d'" % options.piece_length)

    # Do the main work now.
    # -> prepare the metainfo dictionary.
    if os.path.isfile(node):
        info = create_single_file_info(node, piece_length, options.include_md5)
    else:
        info = create_multi_file_info(node, torrent_files, piece_length, options.include_md5)

    assert len(info['pieces']) % 20 == 0, "len(pieces) not a multiple of 20"

    # ###########################
    # FINISH METAINFO DICTIONARY:
    # - info
    #   - piece length
    #   - name (eventually overwrite)
    #   - private
    # - announce
    # - announce-list (if multiple trackers)
    # - creation date (may be disabled as well)
    # - created by
    # - comment (may be disabled as well (if ADVERTISE = False))

    # Finish sub-dict "info".
    info['piece length'] = piece_length

    if options.private:
        info['private'] = 1

    # Construct outer metainfo dict, which contains the torrent's whole
    # information.
    metainfo =  {
                'info':           info,
                'announce':       trackers[0],
                }

    # Make "announce-list" field, if there are multiple trackers.
    if len(trackers) > 1:
        metainfo['announce-list'] = [[tracker] for tracker in trackers]

    # Set "creation date".
    # The user may specify a custom creation date. He may also decide not
    # to include the creation date field at all.
    if   options.date == -1:
        # use current time
        metainfo['creation date'] = int(time.time())
    elif options.date >= 0:
        # use specified timestamp directly
        metainfo['creation date'] = options.date

    # Add the "created by" field.
    metainfo['created by'] = 'py3createtorrent v%s' % VERSION

    # Add user's comment or advertise py3createtorrent (unless this behaviour
    # has been disabled by the user).
    # The user may also decide not to include the comment field at all
    # by specifying an empty comment.
    if isinstance(options.comment, str):
        if len(options.comment) > 0:
            metainfo['comment'] = options.comment
    elif ADVERTISE:
        metainfo['comment'] = "created with " + metainfo['created by']

    # Add the name field.
    # By default this is the name of directory or file the torrent
    # is being created for.
    if options.name:
        options.name = options.name.strip()

        regexp = re.compile("^[A-Z0-9_\-\., ]+$", re.I)

        if not regexp.match(options.name):
            parser.error("Invalid name: '%s'. Allowed chars: A_Z, a-z, 0-9, "
                         "any of {.,_-} plus spaces." % options.name)

        metainfo['info']['name'] = options.name

    # ###################################################
    # BENCODE METAINFO DICTIONARY AND WRITE TORRENT FILE:
    # - take into consideration the --output option
    # - properly handle KeyboardInterrups while writing the file

    # Respect the custom output location.
    if not options.output:
        # Use current directory.
        output_path = metainfo['info']['name'] + ".torrent"

    else:
        # Use the directory or filename specified by the user.
        options.output = os.path.abspath(options.output)

        # The user specified an output directory:
        if os.path.isdir(options.output):
            output_path = os.path.join(options.output,
                                       metainfo['info']['name']+".torrent")
            if os.path.isfile(output_path):
                if not options.force and os.path.exists(output_path):
                    if "yes" != input("'%s' does already exist. Overwrite? "
                                      "yes/no: " % output_path):
                        parser.error("Aborted.")

        # The user specified a filename:
        else:
            # Is there already a file with this path? -> overwrite?!
            if os.path.isfile(options.output):
                if not options.force and os.path.exists(options.output):
                    if "yes" != input("'%s' does already exist. Overwrite? "
                                      "yes/no: " % options.output):
                        parser.error("Aborted.")

            output_path = options.output


    # Actually write the torrent file now.
    try:
        with open(output_path, "wb") as fh:
            fh.write(bencode(metainfo))
    except IOError as exc:
        print("IOError: " + str(exc), file=sys.stderr)
        print("Could not write the torrent file. Check torrent name and your "
              "privileges.", file=sys.stderr)
        print("Absolute output path: '%s'" % os.path.abspath(output_path),
              file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        # Properly handle KeyboardInterrupts.
        # todo: open()'s context manager may already do this on his own?
        if os.path.exists(output_path):
            os.remove(output_path)

    # #########################
    # PREPARE AND PRINT SUMMARY
    # - but check quiet option

    # If the quiet option has been set, we're already finished here,
    # because we don't print a summary in this case.
    if options.quiet:
        return 0

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
    if torrent_size > 10*MIB:
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
    print("  Name:             %s\n"
          "  Size:             %s\n"
          "  Pieces:           %d x %d KiB\n"
          "  Comment:          %s\n"
          "  Private:          %s\n"
          "  Creation date:    %s\n"
          "  Primary tracker:  %s\n"
          "  Backup trackers:\n"
          "%s"
      % (metainfo['info']['name'],
         size,
         piece_count,
         piece_length / KIB,
         metainfo['comment'] if 'comment'       in metainfo else "(none)",
         "yes" if options.private else "no",
         creation_date,
         metainfo['announce'],
         backup_trackers))

    return 0

if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
