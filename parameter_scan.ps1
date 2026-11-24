$TargetDir = "./tests/random_folder_benchmark"
$OutFile = "./benchmark.torrent"

hyperfine --warmup 1 --runs 2 `
  --prepare "rammap -Et & del /f /q benchmark.torrent 2>nul || exit /b 0" `
  --export-json parameter_scan.json `
  --export-markdown parameter_scan.md `
  -L threads 4,8,12,16 `
  -L piecesize 4096,8192,16384 `
  "python ./src/py3createtorrent.py --protocol v1 -p {piecesize} -o $OutFile --threads {threads} $TargetDir"
