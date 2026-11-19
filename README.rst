py3createtorrent
================

*Create torrents via command line!*

py3createtorrent is a comprehensive shell/commandline utility for creating torrents (Linux & Windows).

Features
--------

Some of the features:

- supports **BitTorrent v1, v2, and hybrid** torrents (BEP 52)
- create torrents with **multiple trackers** or **trackerless torrents**
- **automatically choose the most reliable trackers** from `ngosang/trackerslist <https://github.com/ngosang/trackerslist>`_
- add **webseeds** to torrents
- create **private torrents** (disabled DHT, ...)
- **exclude specific files/folders**
- exclude files/folders based on **regular expressions**
- specify **custom piece sizes**
- specify custom creation dates

Basic usage
-----------

Creating a torrent is as simple as::

    py3createtorrent -t udp://tracker.opentrackr.org:1337/announce file_or_folder

The shortcut ``bestN`` can be used for conveniently adding the best N trackers
from `ngosang/trackerslist <https://github.com/ngosang/trackerslist>`_. Example::

    py3createtorrent -t best3 file_or_folder

Multiple trackers can also be specified manually by using ``-t`` multiple times, for example::

    py3createtorrent -t udp://tracker.opentrackr.org:1337/announce -t udp://tracker.cyberia.is:6969/announce file_or_folder

Install
-------

py3createtorrent requires Python 3.11 or later.

**Recommended (isolated CLI installation via uv or pipx):**

Using `uv <https://docs.astral.sh/uv/>`_::

    uv tool install py3createtorrent
    py3createtorrent --help

Or run directly without permanent installation::

    uvx py3createtorrent --help

Using `pipx <https://pipx.pypa.io/>`_::

    pipx install py3createtorrent

Via ``pip``::

    pip install py3createtorrent

Full documentation
------------------

https://py3createtorrent.readthedocs.io/en/latest/user.html
