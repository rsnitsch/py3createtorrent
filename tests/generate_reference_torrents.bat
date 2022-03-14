echo on

call tests\generate_reference_data.bat

FOR %%x IN (16 128 1024 8192) DO python src\py3createtorrent.py --no-created-by -c "" --date -2 tests\testdata\random_folder -p %%x -o tests\referencedata\random_folder_py3createtorrent_p%%x.torrent

FOR %%x IN (16 128 1024 8192) DO python src\py3createtorrent.py --no-created-by -c "" --date -2 tests\testdata\random_file.dat -p %%x -o tests\referencedata\random_file_py3createtorrent_p%%x.torrent

sha1sum tests/referencedata/random_folder*.torrent
sha1sum tests/referencedata/random_file*.torrent
