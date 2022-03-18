copy /Y ..\src\py3createtorrent.py .
docker build . --tag benchmark
docker container rm benchmark
docker container run --name benchmark -v %cd%\results:/results benchmark sh /benchmark/benchmark.sh
