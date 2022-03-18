#!/bin/sh
target=random_file_4gib.dat
python3 create_random_file.py $target 1g

warmup=1
runs=3
threads=1,2,3,4

hyperfine --warmup $warmup --runs $runs --export-csv /results/benchmark_results.csv -L threads $threads -L piece_size 128,1024,8192 --show-output "python3 py3createtorrent.py $target -p {piece_size} --threads {threads}" "transmission-create --piece-size {piece_size} $target"

hyperfine --warmup $warmup --runs $runs --export-csv /results/benchmark_results_torf.csv -L threads $threads -L piece_size 0.125,1,8 --show-output "torf $target --yes --threads {threads} --max-piece-size {piece_size}"

hyperfine --warmup $warmup --runs $runs --prepare "rm *.torrent" --export-csv /results/benchmark_results_mktorrent.csv -L threads $threads -L piece_size 17,20,23 --show-output "mktorrent -t{threads} -l{piece_size} $target"

cd /results
python3 /benchmark/plot_benchmark_results.py benchmark_results.csv benchmark_results_torf.csv benchmark_results_mktorrent.csv
