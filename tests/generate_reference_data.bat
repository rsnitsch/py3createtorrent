echo on

python benchmark\create_random_folder.py tests\testdata\random_folder 200 1k 50m
python benchmark\create_random_file.py tests\testdata\random_file.dat 50m
python benchmark\create_random_file.py tests\testdata\random_file_16k.dat 16k
python benchmark\create_random_file.py tests\testdata\random_file_17k.dat 17k
python benchmark\create_random_file.py tests\testdata\random_file_48k.dat 64k
python benchmark\create_random_file.py tests\testdata\random_file_64k.dat 64k
python benchmark\create_random_file.py tests\testdata\random_file_65k.dat 64k
python benchmark\create_random_file.py tests\testdata\random_file_100k.dat 100k
