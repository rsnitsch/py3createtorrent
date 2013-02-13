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

If you want to disable advertising for a single torrent only, you can remove
the comment field of that torrent completely((unless, of course, you want to
use your own comment)). To achieve this, you can use the --comment option to
specify an empty comment::

   py3createtorrent.py --comment "" ...

Equivalently::

   py3createtorrent.py -c "" ...

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
   Please note: If you do not specify a comment yourself using the -c / --comment
   option, py3createtorrent will advertise itself through the comment field, as
   you can see in the screenshot (Torrent Contents -> Comment: *created with
   py3createtorrent v0.8*).

You can change this behaviour by editing the script. Find ``ADVERTISE = True``
(line ~86) and replace ``True`` by ``False``. See [[#Configuration]].

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