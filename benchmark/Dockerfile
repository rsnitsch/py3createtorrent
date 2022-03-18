FROM debian:stable

WORKDIR /benchmark

RUN apt-get update
RUN apt-get install -y mktorrent transmission-cli python3 python3-pip wget

RUN wget https://github.com/sharkdp/hyperfine/releases/download/v1.13.0/hyperfine_1.13.0_amd64.deb
RUN dpkg -i hyperfine_1.13.0_amd64.deb

RUN pip3 install py3createtorrent torf-cli matplotlib pandas

COPY py3createtorrent.py benchmark.sh create_random_file.py create_random_folder.py plot_benchmark_results.py ./
