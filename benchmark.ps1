# === Config ===
$Threads = 16
$PieceExp = 23 # 2^23 = 8 MiB (20=1MiB, 21=2MiB, 22=4MiB, 23=8MiB, 24=16MiB)
$TargetDir = "./tests/random_folder_benchmark"
$OutFile = "./benchmark.torrent"
$CooldownPingCount = 10

# Piece size specs for the different tools
$PieceBytes = [math]::Pow(2, $PieceExp)
$PieceKiB = $PieceBytes / 1024 # 8192 für py3createtorrent (-p)
$PieceMiB = $PieceKiB / 1024   # 8 für torf-cli (--max-piece-size)

# Create test data
# python .\tests\create_random_folder.py $TargetDir 100 1k 200m

# Execute benchmark (needs admin privileges for rammap -Et)
hyperfine --warmup 1 --runs 5 `
  --prepare "rammap -Et & del /f /q benchmark.torrent 2>nul & ping -n $CooldownPingCount 127.0.0.1 >nul" `
  --export-json benchmark.json `
  --export-markdown benchmark.md `
  -n "py3createtorrent v2.0" "python ./src/py3createtorrent.py --protocol v1 -p $PieceKiB -o $OutFile --threads $Threads $TargetDir" `
  -n "mkbrr" "./mkbrr.exe create -l $PieceExp -o $OutFile --workers $Threads $TargetDir" `
  -n "torf-cli" "torf $TargetDir --threads $Threads --max-piece-size ${PieceMiB} -o $OutFile" `
  -n "torrenttools" "torrenttools create $TargetDir -l $PieceExp -o $OutFile --threads $Threads" `
  @args

# Generate plot
$PlotScript = "./plot_whisker.py"
if (-not (Test-Path $PlotScript)) {
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/sharkdp/hyperfine/master/scripts/plot_whisker.py" -OutFile $PlotScript
}

$PlotUtils = "./plot_utils.py"
if (-not (Test-Path $PlotUtils)) {
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/sharkdp/hyperfine/master/scripts/plot_utils.py" -OutFile $PlotUtils
}

uvx --with matplotlib --with numpy python $PlotScript benchmark.json -o benchmark.png
