import argparse
import os

import matplotlib.pyplot as plt
import pandas as pd


def generate_plot_for_piece_size(df, piece_size):
    df = df[df["parameter_piece_size"] == piece_size].copy()
    df = df.drop(columns="parameter_piece_size")

    TOOLS = ["py3createtorrent", "torrenttools", "torf"]

    for tool in TOOLS:
        df.loc[df["command"].str.contains(tool), "tool"] = tool

    df = df.drop(columns="command")
    df = df.set_index(["parameter_threads", "tool"])

    tools = df.index.unique(level=1)
    threads = df.index.unique(level=0)
    max_threads = max(threads)

    fig, ax = plt.subplots(1, 1, figsize=(8, 6))

    for idx, tool in enumerate(tools):
        mean = df.loc[df.index.get_level_values(1) == tool, "mean"]
        stddev = df.loc[df.index.get_level_values(1) == tool, "stddev"]
        ax.plot(threads, mean)
        #ax.errorbar(threads, mean, stddev, linestyle='None', marker='x')

    fig.suptitle("Performance (lower = faster)", fontsize=20)
    ax.set_title("Piece size = %d KiB" % piece_size)
    ax.set_xlabel("Number of threads for hashing")
    ax.set_ylabel("Time in s")
    ax.set_xticks(list(range(1, max_threads + 1)))
    ax.legend(tools, loc='upper right')

    fig.savefig("plot_for_piece_size_%dk.png" % piece_size, dpi=125)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results_file", help="path to CSV file with the results", nargs='+')

    args = parser.parse_args()

    for file in args.results_file:
        if not os.path.isfile(file):
            parser.error("The specified results file does not exist: " + file)

    df = None
    for file in args.results_file:
        df_file = pd.read_csv(file)
        if df is None:
            df = df_file
        else:
            df = pd.concat([df, df_file])

    # Normalize piece sizes of torf
    #print(df[df["command"].str.contains("torf")].head())
    df.loc[df["command"].str.contains("torf"), "parameter_piece_size"] *= 2**10

    #print(df)
    piece_sizes = df["parameter_piece_size"].unique()

    plt.style.use('ggplot')
    for p in piece_sizes:
        print("Generating plot for piece size %s" % p)
        generate_plot_for_piece_size(df.copy(), p)
        print()


if __name__ == '__main__':
    main()
