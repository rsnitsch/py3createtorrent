python create_random_file.py ../testdata/random_file_15gib.dat 15g

set target=../testdata/random_file_15gib.dat
set warmup=1
set runs=4
set threads=1,2,3,4,5,6

hyperfine --warmup %warmup% --runs %runs% --export-csv benchmark_results.csv -L threads %threads% -L piece_size 128,1024,8192 "python ../src/py3createtorrent.py %target% -p {piece_size} --threads {threads}" "torrenttools create %target% -v1 --piece-size {piece_size}K --threads {threads}"

hyperfine --warmup %warmup% --runs %runs% --export-csv benchmark_results_torf.csv -L threads %threads% -L piece_size 0.125,1,8 --show-output "torf %target% --yes --threads {threads} --max-piece-size {piece_size}"

python plot_benchmark_results.py benchmark_results.csv benchmark_results_torf.csv
