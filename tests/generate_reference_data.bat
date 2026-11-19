echo on

python benchmark\create_random_folder.py tests\testdata\random_folder_big_files 30 1k 10m
python benchmark\create_random_folder.py tests\testdata\random_folder_tiny_files 200 1k 200k
python benchmark\create_random_file.py tests\testdata\random_file.dat 50m
python benchmark\create_random_file.py tests\testdata\random_file_16k.dat 16k
python benchmark\create_random_file.py tests\testdata\random_file_17k.dat 17k
python benchmark\create_random_file.py tests\testdata\random_file_48k.dat 48k
python benchmark\create_random_file.py tests\testdata\random_file_64k.dat 64k
python benchmark\create_random_file.py tests\testdata\random_file_65k.dat 65k
python benchmark\create_random_file.py tests\testdata\random_file_100k.dat 100k
