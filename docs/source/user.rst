py3createtorrent
================

*Create torrents via command line!*

py3createtorrent is a comprehensive shell/commandline utility for creating torrents (Linux & Windows).

Features
--------

Some of the features:

* create torrents with **multiple trackers** or **trackerless torrents**
* **automatically choose the most reliable trackers** from `ngosang/trackerslist <https://github.com/ngosang/trackerslist>`_
* fast torrent creation thanks to **multithreading**
* add **webseeds** to torrents
* create **private torrents** (disabled DHT, ...)
* **exclude specific files/folders**
* exclude files/folders based on **regular expressions**
* specify **custom piece sizes**
* specify custom creation dates

Requirements
------------

py3createtorrent requires at least Python 3.5 and the `bencode.py <https://pypi.org/project/bencode.py/>`_ module.

.. note::

  It may be possible to use the script with older Python versions. For Python 3.2, 3.3, 3.4 you need to install
  the backport of Python's ``typing`` module: https://pypi.org/project/typing/. For Python 3.1 you need to
  additionally install the backport of Python's ``argparse`` module: https://pypi.org/project/argparse/.

  This has not been tested, though. Feedback is welcome.

Installation
------------

Recommended: Installation using pip
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

pip is the easiest and recommended way of installing py3createtorrent.

Just execute::

  pip3 install py3createtorrent

After that, you can use py3createtorrent on your commandline.

Alternative: Manual installation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Alternatively, you can download py3createtorrent manually. Download the desired version from here:
https://github.com/rsnitsch/py3createtorrent/releases

And then install the dependencies::

  pip install bencode.py

Then you can execute py3createtorrent.py (it is in the ``src`` folder).

Alternatively, use pipenv::

  pipenv install

Then you can execute py3createtorrent.py with pipenv as follows::

  pipenv run src/py3createtorrent.py

Basic usage
-----------

Creating a torrent is as simple as::

    py3createtorrent -t udp://tracker.opentrackr.org:1337/announce file_or_folder

The shortcut ``bestN`` can be used for conveniently adding the best N trackers
from `ngosang/trackerslist <https://github.com/ngosang/trackerslist>`_. Example::

    py3createtorrent -t best3 file_or_folder

Multiple trackers can also be specified manually by using `-t` multiple times, for example::

    py3createtorrent -t udp://tracker.opentrackr.org:1337/announce -t udp://tracker.coppersurfer.tk:6969/announce file_or_folder

Full usage guide
----------------

Syntax:

.. code-block:: none

    usage: py3createtorrent.py <target> [-t tracker_url] [options ...]
    
    py3createtorrent is a comprehensive command line utility for creating torrents.
    
    positional arguments:
      target <path>         File or folder for which to create a torrent
    
    optional arguments:
      -h, --help            show this help message and exit
      -t TRACKER_URL, --tracker TRACKER_URL
                            Add one or multiple tracker (announce) URLs to
                            the torrent file.
      --node HOST,PORT      Add one or multiple DHT bootstrap nodes.
      -p PIECE_LENGTH, --piece-length PIECE_LENGTH
                            Set piece size in KiB. [default: 0 = automatic selection]
      -P, --private         Set the private flag to disable DHT and PEX.
      -c COMMENT, --comment COMMENT
                            Add a comment.
      -s SOURCE, --source SOURCE
                            Add a source tag.
      -f, --force           Overwrite existing .torrent files without asking and
                            disable the piece size, tracker and node validations.
      -v, --verbose         Enable output of diagnostic information.
      -q, --quiet           Suppress output, e.g. don't print summary
      -o PATH, --output PATH
                            Set the filename and/or output directory of the
                            created file. [default: <name>.torrent]
      -e PATH, --exclude PATH
                            Exclude a specific path (can be repeated to exclude
                            multiple paths).
      --exclude-pattern REGEXP
                            Exclude paths matching a regular expression (can be repeated
                            to use multiple patterns).
      --exclude-pattern-ci REGEXP
                            Same as --exclude-pattern but case-insensitive.
      -d TIMESTAMP, --date TIMESTAMP
                            Overwrite creation date. This option expects a unix timestamp.
                            Specify -2 to disable the inclusion of a creation date completely.
                            [default: -1 = current date and time]
      -n NAME, --name NAME  Set the name of the torrent. This changes the filename for
                            single file torrents or the root directory name for multi-file torrents.
                            [default: <basename of target>]
      --threads THREADS     Set the maximum number of threads to use for hashing pieces.
                            py3createtorrent will never use more threads than there are CPU cores.
                            [default: 4]
      --md5                 Include MD5 hashes in torrent file.
      --config CONFIG       Specify location of config file.
                            [default: <home directiory>/.py3createtorrent.cfg]
      --webseed WEBSEED_URL
                            Add one or multiple HTTP/FTP urls as seeds (GetRight-style).
      --version             Show version number of py3createtorrent

Specifying trackers (``-t``, ``--tracker``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

One or multiple tracker URLs can be specified using the ``-t`` or ``--tracker`` switch. Single tracker example::

    py3createtorrent -t udp://tracker.opentrackr.org:1337/announce my_data_folder/

This is equivalent to the short form using the :ref:`tracker abbreviation <tracker_abbreviations>` for opentrackr.org::

    py3createtorrent -t opentrackr my_data_folder/

For multiple trackers, just use ``-t`` repeatedly. Multiple tracker example::

    py3createtorrent -t udp://tracker.opentrackr.org:1337/announce -t udp://tracker.coppersurfer.tk:6969/announce -t udp://tracker.cyberia.is:6969/announce my_data_folder/

This is equivalent to the short form using the tracker abbreviations::

    py3createtorrent -t opentrackr -t coppersurfer -t cyberia my_data_folder/

.. automatically_add_best_trackers:

.. _bestN_shortcut:

bestN: Automatically add the best trackers
""""""""""""""""""""""""""""""""""""""""""

You can use ``bestN`` to add the best N trackers from https://github.com/ngosang/trackerslist. This requires internet access, obviously.

For example::

    py3createtorrent -t best5 my_data_folder/

Trackerless torrents
""""""""""""""""""""

You can create a trackerless torrent by not specifying any tracker URLs at all (i.e. don't
use the ``-t`` switch at all).

Specifying DHT bootstrap nodes (``--node``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

One or multiple DHT bootstrap nodes can be specified using the ``--node`` switch. Each bootstrap node must be
specified in the form ``host,port``. Just like ``-t``, the ``--node`` switch can be used repeatedly in order
to specify multiple DHT bootstrap nodes.

Example::

    py3createtorrent --node router.bittorrent.com,8991 --node second.node.com,1337 my_data_folder/

It is recommended to specify some DHT bootstrap nodes for trackerless torrents.

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

Source (``-s``)
^^^^^^^^^^^^^^^

The source field is a non-standard metainfo field used by private trackers to
reduce issues (such as misreported stats) caused by cross-seeding.  For
private trackers that forbid their torrent files from being uploaded elsewhere,
it ensures that torrent files uploaded to the tracker from a different source
are unique to the private tracker.

*New in 0.9.7.*

Force (``-f``)
^^^^^^^^^^^^^^

The force option makes py3createtorrent

- overwrite existing .torrent files without asking for your permission
- disable checking for uncommon and possibly unsupported piece sizes
- disable checking for possibly invalid tracker specifications
- disable checking for possibly invalid node specifications

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

On Windows, this is case-insensitive.

Exclude pattern (``--exclude-pattern``, ``--exclude-pattern-ci``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This allows for the exclusion of files or directories that match a certain
pattern (regular expression).

The switches may be used repeatedly to specify multiple exclusion patterns.

*New in version 0.9.5:* The ``--exclude-pattern-ci`` variant (case-insensitive).
On Windows, the ``--exclude-pattern`` has been made case-sensitive (previously
it was case-insensitive on Windows and case-sensitive on UNIX etc.).

Creation date (``-d``)
^^^^^^^^^^^^^^^^^^^^^^

This switch allows you to overwrite the creation date saved in the .torrent
file. You can fake any creation date you like.

The creation date is specified as `UNIX timestamp
<https://en.wikipedia.org/wiki/Unix_time>`_.

You can disable storing a creation date altogether by providing a timestamp
of -2.

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

Threads (``--threads``)
^^^^^^^^^^^^^^^^^^^^^^^

This controls the *maximum* number of parallel threads that will be used during torrent
creation. Namely, for hashing the pieces.

py3createtorrent will never use more threads than there are CPU cores on your system.

By default py3createtorrent will try to use up to 4 threads for hashing the pieces
of the torrent.

MD5 hashes (``--md5``)
^^^^^^^^^^^^^^^^^^^^^^

As of py3createtorrent 0.9.5 the calculation of MD5 hashes must be explicitly
requested, because it significantly slows down the torrent creation process (and
makes the torrent file a little larger, although this is probably negligible).

*New in 0.9.5.*

Path to config (``--config``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

By default, py3createtorrent tries to load the config file ``.py3createtorrent.cfg``
from the user's home directory. To use another config file, specify the path with
``--config``. Use ``--verbose`` for troubleshooting this, if it does not work as
expected.

*New in 1.0.0.*

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

   C:\Users\Robert\Desktop\Python\createtorrent>py3createtorrent example -t udp://tracker.opentrackr.org:1337/announce

Alternative, equivalent command using a tracker abbreviation for convenience::

   C:\Users\Robert\Desktop\Python\createtorrent>py3createtorrent example -t opentrackr

**Effect**:
Creates example.torrent inside the current directory.

In µTorrent it will look like this:

.. image:: _static/example1.png

.. note::
   Please note: If you do not specify a comment yourself using the ``-c`` / ``--comment``
   option, py3createtorrent will advertise itself through the comment field, as
   you can see in the screenshot (Torrent Contents -> Comment: *created with
   py3createtorrent v0.8*).

   To change this behavior, consult the :ref:`configuration` section.

Example 2 - from directory, excluding subfolders
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Command**::

   C:\Users\Robert\Desktop\Python\createtorrent>py3createtorrent -e example\subfolder example -t udp://tracker.opentrackr.org:1337/announce

**Effect**:
Creates example.torrent inside the current directory. example\subfolder has
been excluded.

.. tip::
   Of course you can exclude multiple subfolders, e.g.::

      py3createtorrent -e exclusion1 -e exclusion2 yourfolder -t tracker-url

In µTorrent it will look like this:

.. image:: _static/example2.png

Example 3 - from directory, excluding files
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Command**::

   C:\Users\Robert\Desktop\Python\createtorrent>py3createtorrent -e example\anotherimage.jpg -e example\subfolder\10_more_minutes_please.JPG example -t udp://tracker.opentrackr.org:1337/announce

Alternative, equivalent command using **regular expressions** instead of
specifying each jpg seperately (also using a tracker abbreviation to make it
even shorter)::

   C:\Users\Robert\Desktop\Python\createtorrent>py3createtorrent --exclude-pattern "(jpg|JPG)$" example -t opentrackr

**Effect**:
Creates example.torrent inside the current directory. example\anotherimage.jpg
and example\subfolder\10_more_minutes_please.JPG have been excluded.

In µTorrent it will look like this:

.. image:: _static/example3.png

Creating torrents of single files
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It's almost the same as for creating directories, except, of course, you can't
use the exclude-option anymore.

.. _configuration:

Configuration
-------------

If present, the configuration file '.py3createtorrent.cfg' will be loaded from the user's
home directory. The configuration file uses JSON format. Use ``--config`` to load the config
from another location. Use ``--verbose`` for troubleshooting this, if it does not work as
expected.

.. warning::

  Before version 1.0, the configuration had to be changed by manually editing the py3createtorrent.py
  script file. If you're still using version 0.x, please upgrade or switch to the old documentation
  of the 0.x branch.

Default
^^^^^^^

If the configuration file is not present, the following default values will be used:

.. code-block:: json

    {
      "best_trackers_url": "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_best.txt",
      "tracker_abbreviations": {
        "opentrackr": "udp://tracker.opentrackr.org:1337/announce",
        "coppersurfer": "udp://tracker.coppersurfer.tk:6969/announce",
        "cyberia": "udp://tracker.cyberia.is:6969/announce"
      },
      "advertise": true
    }

For details on the individual configuration parameters, please refer to the following sub-sections.

Best trackers URL
^^^^^^^^^^^^^^^^^

You can change the URL from which the best tracker URLs are loaded when using the :ref:`bestN shortcut <bestN_shortcut>`.
The default URL is::

    https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_best.txt

To change it, you can use a config file like this:

.. code-block:: json

    {
      "best_trackers_url": "https://ngosang.github.io/trackerslist/trackers_best_ip.txt"
    }

.. _tracker_abbreviations:

Tracker abbreviations
^^^^^^^^^^^^^^^^^^^^^

Tracker abbrevations allow you to specify one or more tracker URLs with a single
word, like 'opentrackr' in the default configuration. They add a lot of convenience,
e.g. look at this neat & clear command::

   C:\Users\Robert\Desktop\Python\createtorrent>py3createtorrent example -t opentrackr -t coppersurfer
   Successfully created torrent:
     Name:             example
    (...)
     Primary tracker:  udp://tracker.opentrackr.org:1337/announce
     Backup trackers:
       udp://tracker.coppersurfer.tk:6969/announce

In this case, py3createtorrent recognizes the tracker abbreviations 'opentrackr' and
'coppersurfer' and automatically inserts the according tracker announce URLs.

.. note::

   Single abbreviations may be replaced by multiple tracker announce URLs. This
   way you can also create sort of "tracker groups" for different kinds of
   torrents.

   Example configuration:
   
   .. code-block:: json

    {
        "tracker_abbreviations": {
            "mytrackergroup": [
                "udp://tracker.opentrackr.org:1337/announce",
                "udp://tracker.coppersurfer.tk:6969/announce"
            ],
            "opentrackr": "udp://tracker.opentrackr.org:1337/announce",
            "coppersurfer": "udp://tracker.coppersurfer.tk:6969/announce"
        }
    }

   Just specify lists of announce URLs instead of a single announce URL to define
   such groups.

Advertise setting
^^^^^^^^^^^^^^^^^

The ``advertise`` setting defines whether py3createtorrent is allowed to advertise
itself through the comment field, if the user hasn't specified a comment. Possible
values are ``true`` (the default) or ``false`` - without any quotes.

To disable advertising, you can use the following in your config file:

.. code-block:: json

    {
      "advertise": false
    }

If you want to disable advertising for a single torrent only, you can use the
``--comment`` option to specify an empty comment::

   $ py3createtorrent --comment "" ...

   or

   $ py3createtorrent -c "" ...

py3createtorrent will not advertise itself in this case, because you explicitly
specified the empty comment.