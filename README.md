py3createtorrent
================

*Create torrents via command line!*

py3createtorrent is a comprehensive shell/commandline utility for creating torrents (Linux & Windows).

Features
--------

Some of the features:

* you can create **huge torrents** for any amount of data
* you can add a **comment** to the torrent file
* you can create **private torrents** (disabled DHT, ...)
* you can create torrents with **multiple trackers**
* you can create **trackerless torrents** (not yet released, but already implemented in develop branch)
* you can add **webseeds** to torrents
* you can **exclude specific files/folders**
* you can exclude files/folders based on **regular expressions**
* you can specify **custom piece sizes**
* you can specify custom creation dates

Basic usage
-----------

Creating a torrent is as simple as:

    py3createtorrent -t udp://tracker.opentrackr.org:1337/announce file_or_folder

Multiple trackers can be specified by using `-t` multiple times, for example:

    py3createtorrent -t udp://tracker.opentrackr.org:1337/announce -t udp://tracker.coppersurfer.tk:6969/announce file_or_folder

Install
-------

You can install py3createtorrent by executing:

    pip3 install py3createtorrent

Of course, you need to have Python 3 installed on your system. py3createtorrent requires Python 3.5 or later.

Full documentation
------------------

https://py3createtorrent.readthedocs.io/en/latest/user.html
