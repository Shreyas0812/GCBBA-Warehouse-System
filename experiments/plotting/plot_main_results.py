"""
plot_main_results.py
====================
Plots primary metrics from a completed steady-state experiment summary.csv.

Averages over seeds. By default plots all comm_ranges as a grid
(rows = comm_range, cols = metric). Pass --comm-ranges to restrict.

Primary metrics plotted:
  1. Throughput vs task_arrival_rate  (one line per algorithm)
  2. avg_task_wait_time vs task_arrival_rate

Usage:
    python experiments/plotting/plot_main_results.py --csv path/to/summary.csv
    python experiments/plotting/plot_main_results.py --csv path/to/summary.csv --save
    python experiments/plotting/plot_main_results.py --csv path/to/summary.csv --comm-ranges 51
    python experiments/plotting/plot_main_results.py --csv path/to/summary.csv --comm-ranges 3 8 51
"""

import argparse
import os

import pandas as pd
import matplotlib.pyplot as plt

ALG_ORDER = ["gcbba", "cbba", "dmchba", "sga"]
ALG_LABELS = {"gcbba": "GCBBA", "cbba": "CBBA", "dmchba": "DMCHBA", "sga": "SGA"}
ALG_COLORS = {"gcbba": "#1f77b4", "cbba": "#ff7f0e", "dmchba": "#2ca02c", "sga": "#d62728"}

METRICS = [
    ("throughput",       "throughput (tasks/ts)",    "Throughput"),
    ("avg_task_wait_time", "avg task wait time (ts)", "Avg Task Wait Time"),
]


def infer_map_name(csv_path: str) -> str:
    """Infer map name from path: .../experiments/<map_name>/<timestamp>/summary.csv"""
    parts = os.path.normpath(csv_path).split(os.sep)
    for i, part in enumerate(parts):
        if part == "experiments" and i + 2 < len(parts):
            return parts[i + 1]
    return "unknown_map"


def load(csv_path: str, comm_ranges: list) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df = df[df["hit_timestep_ceiling"] & ~df["hit_wall_clock_ceiling"]]
    if comm_ranges:
        df = df[df["comm_range"].isin(comm_ranges)]
    return df


MIN_SEEDS = 3


def mean_by_ar(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    grp = df.groupby(["allocation_method", "task_arrival_rate"])
    counts = grp[metric].count().reset_index(name="_n")
    means = grp[metric].mean().reset_index()
    merged = means.merge(counts, on=["allocation_method", "task_arrival_rate"])
    return merged[merged["_n"] >= MIN_SEEDS].drop(columns="_n")


def plot(csv_path: str, comm_ranges: list, save: bool = False):
    df = load(csv_path, comm_ranges)
    if df.empty:
        print("No valid rows after filtering.")
        return

    map_name = infer_map_name(csv_path)
    output_dir = os.path.dirname(csv_path)
    algorithms = [a for a in ALG_ORDER if a in df["allocation_method"].unique()]

    cr_values = sorted(df["comm_range"].unique())
    n_rows = len(cr_values)
    n_cols = len(METRICS)

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(7 * n_cols, 4 * n_rows),
                             squeeze=False)
    fig.suptitle(f"Algorithm Comparison — {map_name}", fontsize=14)

    for row_idx, cr in enumerate(cr_values):
        cr_df = df[df["comm_range"] == cr]
        for col_idx, (metric, ylabel, title) in enumerate(METRICS):
            ax = axes[row_idx][col_idx]
            agg = mean_by_ar(cr_df, metric)
            # Keep only arrival rates where all present algorithms have data
            ar_per_alg = [set(agg[agg["allocation_method"] == a]["task_arrival_rate"]) for a in algorithms if not agg[agg["allocation_method"] == a].empty]
            shared_ars = set.intersection(*ar_per_alg) if ar_per_alg else set()
            agg = agg[agg["task_arrival_rate"].isin(shared_ars)]
            for alg in algorithms:
                subset = agg[agg["allocation_method"] == alg].sort_values("task_arrival_rate")
                if subset.empty:
                    continue
                ax.plot(subset["task_arrival_rate"], subset[metric],
                        marker="o", markersize=4,
                        label=ALG_LABELS.get(alg, alg),
                        color=ALG_COLORS.get(alg))

            ax.set_xlabel("task arrival rate (tasks/ts/station)", fontsize=8)
            ax.set_ylabel(ylabel, fontsize=8)
            ax.set_title(f"{title}  [cr={cr}]", fontsize=10)
            ax.legend(fontsize=8)
            ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()

    if save:
        tag = "_".join(str(c) for c in cr_values)
        out = os.path.join(output_dir, f"main_results_cr{tag}.png")
        plt.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved: {out}")
    else:
        plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to summary.csv")
    parser.add_argument("--save", action="store_true", help="Save PNG instead of showing")
    parser.add_argument("--comm-ranges", nargs="+", type=int, default=None,
                        help="Comm ranges to plot (default: all in data)")
    args = parser.parse_args()
    plot(args.csv, comm_ranges=args.comm_ranges, save=args.save)
