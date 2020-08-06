Changelog
=========

Version 1.0.0 (not yet released)
--------------------------------

* changed: **requires Python 3.5+ now**
* changed: specifying trackers is now optional with the new ``-t`` switch, thus **trackerless torrents are now
  possible**
* added: DHT bootstrap nodes can now be specified with the new ``--node`` switch (doing so is recommended for
  trackerless torrents)
* added: **webseed support** with the new ``--webseed`` switch (GetRight style, i.e. `<http://bittorrent.org/beps/bep_0019.html>`_)
* changed: increased max piece size to 16 MiB
* changed: show warning if piece size is not a multiple of 16 KiB
* changed: updated the default trackers (openbt is now opentrackr, dropped publicbt, added cyberia and coppersurfer)
* added: Pipfile and Pipfile.lock for pipenv support
* added: README.md
* refactored: switched to bencode.py module for encoding the torrent data
* refactored: switched from optparse to argparse
* refactored: reformatted code with yapf, using a new column limit of 120
* refactored: added type hints to enable analysis with mypy (we use Python's typing module which was added in
  Python 3.5, thus Python 3.5 is the new minimum version that is required)

Version 0.9.7
-------------

*Release date: 2020/07/23*

* new: switch ``--source`` to include a metainfo field 'source', which is required
  by some private trackers (contributed by cpurules)
* changed: slightly improved docs on ``--date`` switch (now mentions the special
  value -2 for disabling the date field altogether)
* changed:  slightly improve handling of negative timestamp values for
  ``--date`` switch

Version 0.9.6
-------------

*Release date: 2019/08/29*

* new: exit gracefully if py3bencode module could not be imported and show
  instructions on how to fix this
* docs: Updated docs after migration from Mercurial/Bitbucket.org to Git/Github.com

Version 0.9.5
-------------

*Release date: 2013/06/04*

* new: switch ``--md5`` to request MD5 hashes; they are now turned off by default,
  resulting in a **significant performance improvement** (af745c8581de)
* new: switch ``--exclude-pattern-ci`` for case-insensitive regular expressions
  (1c68ad21c72f)
* fixed: On Windows, the ``--exclude-pattern`` switch has not been case-sensitive
  (f5c00b9eccbc)
* fixed docs: installation instructions for py3bencode using ``setup.py`` (276a82e1cbc3)

Version 0.9.4
-------------

*Release date: 2013/02/26*

* new: documentation is now part of the repository, based on Sphinx (dd3d74f5cc26 and following)
* fixed: UDP tracker announce urls (c639e2f8408a + 69afadea92e4)
* fixed: piece count calculation (8450c6470d7f)
* fixed: inconsistent number of blank lines after summary (30f870d55c56)

Version 0.9.3
-------------

*Release date: 2010/12/13*

* ! fixed: tracker abbreviations for openbittorrent fixed. **new default abbreviations:
  openbt and publicbt** for openbittorrent and publicbittorrent. Note that both of them
  do no more offer a http announce URL (they are pure UDP trackers now).
* fixed: did not prompt the user when overwriting an existing torrent using the
  -o <output directory> switch
* fixed: version number was still 0.9 (now 0.9.3, of course), so it did not
  identify itself correctly, e.g. when issueing "--version".

Version 0.9.2
-------------

*Release date: 2010/11/09*

* fixed: the private switch (--private / -P) did not have any effect (reported by steven)
* fixed: wrong email address (now ...+dev@gmail.com instead of dev+...@gmail.com)

Version 0.9.1
-------------

*Release date: 2010/10/17*

* !!! fixed: torrents for single files could not be created (reported by JWA)

Version 0.9
-----------

*Release date: 2010/08/19*

* !!! fixed: creating torrents with multiple trackers did not work. the announce-list
  has been created in a wrong way by version 0.8.
* added: possibility to create tracker abbreviations. by default there is 'obt'
  for OBT((Open BitTorrent - an open tracker project))'s announce urls
* added: print summary after writing the torrent file
* added: skipping symlinks that point to files or directories that have already
  been processed (or are still being processed)
* added: -v / --verbose option (reports skipped & processed files)
* added: -q / --quiet option (at the moment this option only removes the summary
  in the end)
* added: you may now use --exclude-pattern to exclude files/folders based on
  regular expressions
* changed: applied `Python Style Guide (PEP 8) <http://www.python.org/dev/peps/pep-0008/>`_
* changed: using ``#!/usr/bin/env python3`` instead of ``#!/usr/bin/python3``
* changed: removed the huge get_size function, there was a better way to go
* fixed: removing duplicate trackers now
* fixed: empty comment now disables comment field (didn't work before)

Version 0.8
-----------

*Release date: 2010/08/10.*

Initial release.
