echo on

python benchmark\create_random_folder.py tests\testdata\random_folder 200 1k 50m
python benchmark\create_random_file.py tests\testdata\random_file.dat 50m
