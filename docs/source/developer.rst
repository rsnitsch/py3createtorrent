Developer documentation
=======================

Todo
----

* find out what Python 3.x versions the script is compatible with
* add the ability to define how the announce-list should be constructed in detail
  (tracker tiers etc., see `Multitracker Metadata
  Extension <http://bittorrent.org/beps/bep_0012.html>`_)
* add webseed support (`Hoffman style <http://bittorrent.org/beps/bep_0017.html>`_ &
  `GetRight style <http://bittorrent.org/beps/bep_0019.html>`_)
* think about integrating the py3bencode module to make it stand-alone
* validate tracker URLs
* improve behaviour when detecting the need for overwriting an existing torrent
  (if the user aborts, the torrent has to be calculated again)
* add switch to make regular expressions case insensitive
* isn't the comment field supposed to be multi-lined?
* create test cases, unit tests, ...
* provide more examples here on this page

Future
------

Some ideas regarding the long-term future:

* create GUI
* make it possible to edit existing torrents
