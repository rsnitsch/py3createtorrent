Developer documentation
=======================

Todo
----

* use configuration files instead of requiring users to edit the script
* add the ability to define how the announce-list should be constructed in detail
  (tracker tiers etc., see `Multitracker Metadata
  Extension <http://bittorrent.org/beps/bep_0012.html>`_)
* add webseed support (`Hoffman style <http://bittorrent.org/beps/bep_0017.html>`_ &
  `GetRight style <http://bittorrent.org/beps/bep_0019.html>`_)
* improve behaviour when detecting the need for overwriting an existing torrent
  (if the user aborts, the torrent has to be calculated again)
* isn't the comment field supposed to be multi-lined?
* create test cases, unit tests, ...
* provide more examples in the documentation

Future
------

Some ideas regarding the long-term future:

* create GUI
* make it possible to edit existing torrents
