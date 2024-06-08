py3createtorrent
================

*Create torrents via command line!*

py3createtorrent is a comprehensive shell/commandline utility for creating torrents (Linux & Windows).

Features
--------

Some of the features:

* create torrents with **multiple trackers** or **trackerless torrents**
* **automatically choose the most reliable trackers** from [ngosang/trackerslist](https://github.com/ngosang/trackerslist)
* fast torrent creation thanks to **multithreading**
* add **webseeds** to torrents
* create **private torrents** (disabled DHT, ...)
* **exclude specific files/folders**
* exclude files/folders based on **regular expressions**
* specify **custom piece sizes**
* specify custom creation dates

Basic usage
-----------

Creating a torrent is as simple as:

    py3createtorrent -t udp://tracker.opentrackr.org:1337/announce file_or_folder

The shortcut ``bestN`` can be used for conveniently adding the best N trackers
from [ngosang/trackerslist](https://github.com/ngosang/trackerslist). Example:

    py3createtorrent -t best3 file_or_folder

Multiple trackers can also be specified manually by using `-t` multiple times, for example:

    py3createtorrent -t udp://tracker.opentrackr.org:1337/announce -t udp://tracker.cyberia.is:6969/announce file_or_folder

Install
-------

You can install py3createtorrent by executing:

    pip3 install py3createtorrent

Of course, you need to have Python 3 installed on your system. py3createtorrent requires Python 3.5 or later. For using
Python 3.5 to 3.7 you need to install the ``typing-extensions`` module.

Full documentation
------------------

https://py3createtorrent.readthedocs.io/en/latest/user.html
