py3createtorrent
================

|pypi| |python| |audit| |docs| |license|

.. |pypi| image:: https://img.shields.io/pypi/v/py3createtorrent.svg
   :target: https://pypi.org/project/py3createtorrent/
   :alt: PyPI

.. |python| image:: https://img.shields.io/pypi/pyversions/py3createtorrent.svg
   :target: https://pypi.org/project/py3createtorrent/
   :alt: Python Versions

.. |audit| image:: https://github.com/rsnitsch/py3createtorrent/actions/workflows/pip-audit.yml/badge.svg?branch=master
   :target: https://github.com/rsnitsch/py3createtorrent/actions/workflows/pip-audit.yml
   :alt: Dependency Security Audit

.. |docs| image:: https://img.shields.io/readthedocs/py3createtorrent/latest.svg
   :target: https://py3createtorrent.readthedocs.io/en/latest/
   :alt: Documentation Status

.. |license| image:: https://img.shields.io/badge/License-LGPL_v3-blue.svg
   :target: https://www.gnu.org/licenses/lgpl-3.0
   :alt: License: LGPL v3

*Create torrents via command line!*

py3createtorrent is a comprehensive shell/commandline utility for creating torrents (Linux & Windows).

Features
--------

Some of the features:

- since **v2.0**: supports **BitTorrent v1, v2, and hybrid** torrents (BEP 52)
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

Install py3createtorrent 2.0 (pre-release)
------------------------------------------

*The 2.0 release is only available as a pre-release (alpha/unstable).*

py3createtorrent 2.0 requires Python 3.11 or later.

**Recommended (isolated CLI installation via uv or pipx):**

Using `uv <https://docs.astral.sh/uv/>`_::

    uv tool install --prerelease=allow py3createtorrent
    py3createtorrent --help

    # or without installation
    uvx --prerelease=allow py3createtorrent --help

Using `pipx <https://pipx.pypa.io/>`_::

    pipx install --pip-args="--pre" py3createtorrent
    py3createtorrent --help
    
    # or without installation
    pipx run --pip-args="--pre" py3createtorrent --help

Via ``pip``::

    pip install --pre py3createtorrent
    py3createtorrent --help

Install py3createtorrent 1.2 (stable)
-------------------------------------

py3createtorrent 1.2 requires Python 3.8 or later. Python 3.5 to Python 3.7 might be possible if you
install the ``typing-extensions`` module.

Note: The stable 1.2 version comes without v2/hybrid torrent support.

**Recommended (isolated CLI installation via uv or pipx):**

Using `uv <https://docs.astral.sh/uv/>`_::

    uv tool install py3createtorrent
    py3createtorrent --help

    # or without installation
    uvx py3createtorrent --help

Using `pipx <https://pipx.pypa.io/>`_::

    pipx install py3createtorrent
    py3createtorrent --help

    # or without installation
    pipx run py3createtorrent --help

Via ``pip``::

    pip install py3createtorrent
    py3createtorrent --help

Full documentation
------------------

For 2.x (unstable/alpha):

https://py3createtorrent.readthedocs.io/en/latest/user.html

For 1.2 (stable):

https://py3createtorrent.readthedocs.io/en/v1.2.1/user.html

Performance
-----------

py3createtorrent v2.0 is one of the fastest torrent creation tools available.

Here are the benchmark results for creating a torrent for a folder containing 10.5 GB in 101 files:

========================= ================== ====== ======
Command                   Mean Wall Time [s] Change Factor
========================= ================== ====== ======
``py3createtorrent v2.0`` 7.516 ± 0.137             
``mkbrr``                 7.133 ± 0.063      -5.1%  
``torf-cli``              9.618 ± 0.096      +28.0% 
``torrenttools``          9.632 ± 0.051      +28.2% 
========================= ================== ====== ======

Plot:

.. image:: :/benchmark.png
   :alt: Plot of benchmark results

System specs:

- AMD Ryzen 7 7735HS (3.2 GHz, 8 cores)
- 16 GB DDR5 RAM
- Micron 2400 SSD

The benchmarking code is in ``.\benchmark.ps1``.
