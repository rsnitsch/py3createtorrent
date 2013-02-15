py3createtorrent
================

*Create torrents via command line!*

py3createtorrent is a comprehensive shell/commandline utility for creating
torrents (Linux & Windows). It's a GPL-licensed Python v3.1 script. I tested it
with Ubuntu 8.04 / rTorrent and Windows 7 / µTorrent.

Some of the features:

* you can create **huge torrents** for any amount of data
* you can add a **comment** to the torrent file
* you can create **private torrents** (disabled DHT, ...)
* you can create torrents with **multiple trackers**
* you can **exclude specific files/folders**
* you can exclude files/folders based on **regular expressions**
* you can specify **custom piece sizes**
* you can specify custom creation dates

Motivation
----------

There already is rTorrent, but unfortunately it does not support creating torrents.
Thus, it is often a pain to seed torrents from your servers directly.

py3createtorrent is intended to fill this gap.

Requirements
------------

py3createtorrent requires at least Python 3.1 and the `py3bencode <https://bitbucket.org/rsnitsch/py3bencode>`_ module.

Installation
------------

Download the desired version from here:
https://bitbucket.org/rsnitsch/py3createtorrent/downloads

If the version you downloaded is >= 0.9.4 you will have to install the
`py3bencode <https://bitbucket.org/rsnitsch/py3bencode>`_ module yourself
(up to 0.9.3 the py3bencode module was shipped with py3createtorrent). See the
section below for instructions.

Installing the py3bencode module
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can either download the ``py3bencode.py`` directly from its bitbucket repository
and place it in the same directory as ``py3createtorrent.py`` or you can use
`pip <http://www.pip-installer.org/>`_ to install the py3bencode module in
your Python installation::

   pip install hg+https://bitbucket.org/rsnitsch/py3bencode

Make sure to use the pip executable that belongs to the Python interpreter
with which you will execute py3createtorrent.

If you don't have pip around (although I strongly recommend using it) you can
also try to install py3bencode manually::

   $ hg clone https://bitbucket.org/rsnitsch/py3bencode
   $ python3 py3bencode/setup.py

.. _configuration:

Configuration
-------------

There is a small configuration section in the script, starting at line 25::

   # #############
   # CONFIGURATION

   # configure your tracker abbreviations here
   TRACKER_ABBR = {'openbt':       'udp://tracker.openbittorrent.com:80/announce',
                   'publicbt':     'udp://tracker.publicbt.com:80/announce'}

   # whether or not py3createtorrent is allowed to advertise itself
   # through the torrents' comment fields
   ADVERTISE = True

   # /CONFIGURATION
   # ##############

Tracker abbreviations
^^^^^^^^^^^^^^^^^^^^^

Tracker abbrevations allow you to specify one or more tracker URLs with a single
word, like 'openbt' in the default configuration. They add a lot of convenience,
e.g. look at this neat & clear command::

   C:\Users\Robert\Desktop\Python\createtorrent>py3createtorrent.py example openbt publicbt
   Successfully created torrent:
     Name:             example
    (...)
     Primary tracker:  udp://tracker.openbittorrent.com/announce
     Backup trackers:
       udp://tracker.publicbt.com:80/announce

In this case, py3createtorrent recognizes the tracker abbreviations 'openbt' and
'publicbt' and automatically inserts the according tracker announce URLs.

.. note::

   Single abbreviations may be replaced by multiple tracker announce URLs. This
   way you can also create sort of "tracker groups" for different kinds of
   torrents.

   Example configuration::

      TRACKER_ABBR = {'mytrackergroup':  ['udp://tracker.openbittorrent.com:80/announce',
                                          'udp://tracker.publicbt.com:80/announce'],
                      'openbt':          'udp://tracker.openbittorrent.com:80/announce',
                      'publicbt':        'udp://tracker.publicbt.com:80/announce'}

   Just specify lists of announce URLs instead of a single announce URL to define
   such groups.

Advertise setting
^^^^^^^^^^^^^^^^^

The ``ADVERTISE`` setting defines whether py3createtorrent is allowed to advertise
itself through the comment field, if the user hasn't specified a comment.

If you want to disable advertising for a single torrent only, you can use the
``--comment`` option to specify an empty comment::

   $ py3createtorrent.py --comment "" ...

   or

   $ py3createtorrent.py -c "" ...

py3createtorrent will not advertise itself in this case, because you explicitly
specified the empty comment.

Usage
-----

Syntax::

   Usage: py3createtorrent.py [options] <file-or-directory> <main-tracker-url> [<backup-tracker-url> ...]

   py3createtorrent is a comprehensive command line utility for creating
   torrents.

   Options:
     --version             show program's version number and exit
     -h, --help            show this help message and exit
     -p PIECE_LENGTH, --piece-length=PIECE_LENGTH
                           piece size in KiB. 0 = automatic selection (default).
     -P, --private         create private torrent
     -c COMMENT, --comment=COMMENT
                           include comment
     -f, --force           dont ask anything, just do it
     -v, --verbose         verbose mode
     -q, --quiet           be quiet, e.g. don't print summary
     -o PATH, --output=PATH
                           custom output location (directory or complete path).
                           default = current directory.
     -e PATH, --exclude=PATH
                           exclude path (can be repeated)
     --exclude-pattern=REGEXP
                           exclude paths matching the regular expression (can be
                           repeated)
     -d TIMESTAMP, --date=TIMESTAMP
                           set creation date (unix timestamp). -1 = now
                           (default). -2 = disable.
     -n NAME, --name=NAME  use this file (or directory) name instead of the real
                           one

Piece size (``-p``)
^^^^^^^^^^^^^^^^^^^

This switch allows you to specify a custom piece size. The piece size should be
chosen with care, because it affects the following properties:

* size of the .torrent file
* network overhead
* cost of fixing corrupted pieces
* time it takes until peers start sharing data

.. note::

   Unless you know what you're doing, please let py3createtorrent automatically
   determine the best piece size for you.

Background
""""""""""

In general, the files for which a .torrent is created are sliced up in **pieces**.

For each piece, a 20-byte checksum (based on SHA-1, the Secure Hash Algorithm 1) is
calculated and stored inside the .torrent file - this, by the way, is the
time-consuming part of torrent creation. Therefore, the piece size strongly
correlates with the size of the created .torrent file: The larger the pieces,
the smaller the number of pieces for which a checksum must be stored (and vice
versa).

The piece size also affects the **network overhead** involved in the peer-2-peer
communication for a torrent. The peers regularly exchange information records
that specify the pieces that each peer has finished downloading so that they know
where they can get certain pieces from. The greater the number of pieces, the
larger these information records need to be and thus the greater the overhead
will tend to be.

Moreover, corrupted pieces need to be redownloaded. Of course, large pieces
are more expensive to redownload (both in terms of time and traffic).

Finally, the piece size also affects the time it takes until peers
start to share data with each other (only pieces that have been downloaded
completely can be shared with other peers). Therefore, if the piece size is
large, it will take longer for any peer to finish downloading a piece and to be
able to share this piece with other peers.

Private torrents (``-P``)
^^^^^^^^^^^^^^^^^^^^^^^^^

Private torrents force the BitTorrent clients to only use the specified trackers
for discovering other peers. Advanced peer discovery methods like DHT or
peer list exchange are effectively disabled.

Comment (``-c``)
^^^^^^^^^^^^^^^^

The comment is a short text stored in the .torrent file and displayed by most
BitTorrent clients in the torrent info.

By default py3createtorrent uses "created by py3createtorrent <version>" as
comment (to change this behavior, consult the :ref:`configuration` section).

Force (``-f``)
^^^^^^^^^^^^^^

Force makes py3createtorrent e.g. overwrite existing .torrent files without
asking for your permission.

Verbose (``-v``)
^^^^^^^^^^^^^^^^

Verbose mode makes py3createtorrent report about the individual steps it is
undertaking while creating the .torrent file.

This is particularly useful for debugging purposes.

Quiet (``-q``)
^^^^^^^^^^^^^^

py3createtorrent will try to stay completely silent on the commandline.

Output path (``-o``)
^^^^^^^^^^^^^^^^^^^^

The output path is either the directory in which the .torrent file should be
saved or the complete path to the destination .torrent file. In the former
case, the name of the .torrent file is deduced from the input's name (i.e.
the input directory's or file's name), unless this name is explicitly
overwritten (using the ``-n`` switch). (In the latter case, the name of the
.torrent file is itself specified by the output path.)

By default, py3createtorrent uses the current working directory as the output
directory.

Exclude path (``-e``)
^^^^^^^^^^^^^^^^^^^^^

This allows for the exclusion of specific files or directories.

The switch may be used repeatedly to exclude multiple files/directories.

Exclude pattern (``--exclude-pattern``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This allows for the exclusion of files or directories that match a certain
pattern (regular expression).

The switch may be used repeatedly to specify multiple exclusion patterns.

Creation date (``-d``)
^^^^^^^^^^^^^^^^^^^^^^

This switch allows you to overwrite the creation date saved in the .torrent
file. You can fake any creation date you like.

The creation date is specified as `UNIX timestamp
<https://en.wikipedia.org/wiki/Unix_time>`_.

Name (``-n``)
^^^^^^^^^^^^^

This setting overwrites the file or directory name stored inside the .torrent
file. **Thus it affects the file or directory name that will be presented
to downloaders as the real name of the data.** You can use it to avoid
renaming your input data.

Unless a destination .torrent file is explicitly specified (using the ``-o`` switch),
this name will also be used to deduce the name of the resulting .torrent file.

.. note::

   The name switch is an advanced feature that most users probably don't need.
   Therefore, please refrain from using this feature, unless you really know
   what you're doing.

   For most intents and purposes, the ``-o`` switch is probably more suitable.

Examples
--------

Assume there is a folder "example" with the following contents::

   example/
     subfolder/
       10_more_minutes_please.JPG
       image.rar
     anotherimage.jpg
     image.zip

Assume, we're currently inside the parent directory.

Example 1 - from directory, no options, default behaviour
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Command**::

   C:\Users\Robert\Desktop\Python\createtorrent>py3createtorrent.py example udp://tracker.openbittorrent.com/announce

Alternative, equivalent command using a tracker abbreviation for convenience::

   C:\Users\Robert\Desktop\Python\createtorrent>py3createtorrent.py example openbt

**Effect**:
Creates example.torrent inside the current directory.

In µTorrent it will look like this:

.. image:: _static/example1.png

.. note::
   Please note: If you do not specify a comment yourself using the ``-c`` / ``--comment``
   option, py3createtorrent will advertise itself through the comment field, as
   you can see in the screenshot (Torrent Contents -> Comment: *created with
   py3createtorrent v0.8*).

   You can change this behaviour by editing the script. Find ``ADVERTISE = True``
   (line ~86) and replace ``True`` by ``False``. See :ref:`configuration`.

Example 2 - from directory, excluding subfolders
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Command**::

   C:\Users\Robert\Desktop\Python\createtorrent>py3createtorrent.py -e example\subfolder example udp://tracker.openbittorrent.com/announce

**Effect**:
Creates example.torrent inside the current directory. example\subfolder has
been excluded.

.. tip::
   Of course you can exclude multiple subfolders, e.g.::

      py3createtorrent.py -e exclusion1 -e exclusion2 yourfolder tracker-url

In µTorrent it will look like this:

.. image:: _static/example2.png

Example 3 - from directory, excluding files
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Command**::

   C:\Users\Robert\Desktop\Python\createtorrent>py3createtorrent.py -e example\anotherimage.jpg -e example\subfolder\10_more_minutes_please.JPG example udp://tracker.openbittorrent.com/announce

Alternative, equivalent command using **regular expressions** instead of
specifying each jpg seperately (also using a tracker abbreviation to make it
even shorter)::

   C:\Users\Robert\Desktop\Python\createtorrent>py3createtorrent.py --exclude-pattern "(jpg|JPG)$" example openbt

**Effect**:
Creates example.torrent inside the current directory. example\anotherimage.jpg
and example\subfolder\10_more_minutes_please.JPG have been excluded.

In µTorrent it will look like this:

.. image:: _static/example3.png

Creating torrents of single files
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It's almost the same as for creating directories, except, of course, you can't
use the exclude-option anymore.