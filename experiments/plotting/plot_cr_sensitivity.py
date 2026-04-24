"""
plot_cr_sensitivity.py
======================
Plots throughput and task_balance_std vs comm_range at fixed arrival rates.
One line per algorithm — shows how each degrades as communication range shrinks.

Usage:
    python experiments/plotting/plot_cr_sensitivity.py --csv path/to/summary.csv
    python experiments/plotting/plot_cr_sensitivity.py --csv path/to/summary.csv --save
    python experiments/plotting/plot_cr_sensitivity.py --csv path/to/summary.csv --arrival-rates 0.0058 0.0116
"""

import argparse
import os

import pandas as pd
import matplotlib.pyplot as plt

ALG_ORDER  = ["gcbba", "cbba", "dmchba", "sga"]
ALG_LABELS = {"gcbba": "LCBA", "cbba": "CBBA", "dmchba": "DMCHBA", "sga": "SGA"}
ALG_COLORS = {"gcbba": "#1f77b4", "cbba": "#ff7f0e", "dmchba": "#2ca02c", "sga": "#d62728"}

MIN_SEEDS = 2

METRICS = [
    ("throughput",      "throughput (tasks/ts)",  "Throughput vs Comm Range"),
    ("task_balance_std","task balance std",        "Task Balance Std vs Comm Range"),
]


def infer_map_name(csv_path: str) -> str:
    parts = os.path.normpath(csv_path).split(os.sep)
    for i, part in enumerate(parts):
        if part == "experiments" and i + 2 < len(parts):
            return parts[i + 1]
    return "unknown_map"


def load(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    return df[df["hit_timestep_ceiling"] & ~df["hit_wall_clock_ceiling"]]


def mean_by_cr(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    grp = df.groupby(["allocation_method", "comm_range"])
    counts = grp[metric].count().reset_index(name="_n")
    means  = grp[metric].mean().reset_index()
    merged = means.merge(counts, on=["allocation_method", "comm_range"])
    return merged[merged["_n"] >= MIN_SEEDS].drop(columns="_n")


def plot(csv_path: str, arrival_rates: list, save: bool = False):
    df = load(csv_path)
    map_name   = infer_map_name(csv_path)
    output_dir = os.path.dirname(csv_path)

    # Default: all arrival rates with full coverage if not specified
    if not arrival_rates:
        pivot    = df.groupby(["comm_range", "task_arrival_rate", "allocation_method"]).size().reset_index(name="n")
        pivot    = pivot[pivot["n"] >= MIN_SEEDS]
        complete = pivot.groupby(["comm_range", "task_arrival_rate"])["allocation_method"].count().reset_index(name="n_algs")
        n_cr     = df["comm_range"].nunique()
        full     = complete[complete["n_algs"] == df["allocation_method"].nunique()]
        ar_counts = full.groupby("task_arrival_rate")["comm_range"].count()
        arrival_rates = sorted(ar_counts[ar_counts == n_cr].index.tolist())
        arrival_rates = [ar for ar in arrival_rates if ar > 0]  # skip ar=0

    if not arrival_rates:
        print("No arrival rates with complete coverage found.")
        return

    algorithms = [a for a in ALG_ORDER if a in df["allocation_method"].unique()]
    n_rows = len(arrival_rates)
    n_cols = len(METRICS)

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(7 * n_cols, 4 * n_rows), squeeze=False)
    fig.suptitle(f"Comm Range Sensitivity — {map_name}", fontsize=14)

    for row_idx, ar in enumerate(arrival_rates):
        ar_df = df[df["task_arrival_rate"] == ar]
        for col_idx, (metric, ylabel, title) in enumerate(METRICS):
            ax  = axes[row_idx][col_idx]
            agg = mean_by_cr(ar_df, metric)
            for alg in algorithms:
                subset = agg[agg["allocation_method"] == alg].sort_values("comm_range")
                if subset.empty:
                    continue
                ax.plot(subset["comm_range"], subset[metric],
                        marker="o", markersize=5,
                        label=ALG_LABELS.get(alg, alg),
                        color=ALG_COLORS.get(alg))

            ax.set_xlabel("comm_range", fontsize=9)
            ax.set_ylabel(ylabel, fontsize=9)
            ax.set_title(f"{title}  [ar={ar:.4f}]", fontsize=10)
            ax.legend(fontsize=9)
            ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()

    if save:
        ar_tag = "_".join(f"{ar:.4f}" for ar in arrival_rates)
        out = os.path.join(output_dir, f"cr_sensitivity_ar{ar_tag}.png")
        plt.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved: {out}")
    else:
        plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to summary.csv")
    parser.add_argument("--save", action="store_true", help="Save PNG instead of showing")
    parser.add_argument("--arrival-rates", nargs="+", type=float, default=None,
                        help="Fixed arrival rates to plot (default: auto-detect complete ones)")
    args = parser.parse_args()
    plot(args.csv, arrival_rates=args.arrival_rates, save=args.save)
