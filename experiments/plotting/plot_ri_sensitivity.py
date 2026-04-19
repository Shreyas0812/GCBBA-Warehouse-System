"""
plot_ri_sensitivity.py
======================
Plots rerun_interval sensitivity results from summary.csv.

Currently plots only the two primary metrics needed to decide optimal ri:
  1. Throughput vs rerun_interval (one line per arrival rate)
  2. Interval-triggered allocation calls vs rerun_interval

Secondary metrics available in summary.csv but not yet plotted:
  avg_task_wait_time, avg_queue_depth, queue_saturation_fraction,
  avg_gcbba_time_ms, avg_idle_ratio, task_balance_std

Usage:
    python experiments/plotting/plot_ri_sensitivity.py --csv path/to/summary.csv
    python experiments/plotting/plot_ri_sensitivity.py --csv path/to/summary.csv --save
"""

import argparse
import os
import sys

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

RI_LABEL = {999999: "disabled"}  # display label for the sentinel value


def ri_display(val):
    return RI_LABEL.get(val, str(val))


def load(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # Drop runs that hit the timestep ceiling (incomplete) but keep wall-clock-limited
    # runs — throughput is normalized per-timestep so wall-clock hits are still valid.
    df = df[~df["hit_timestep_ceiling"]]
    return df


def mean_by_ri(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Mean of metric across seeds, grouped by (task_arrival_rate, rerun_interval)."""
    return (
        df.groupby(["task_arrival_rate", "rerun_interval"])[metric]
        .mean()
        .reset_index()
    )


def infer_map_name(csv_path: str) -> str:
    """Infer map name from the CSV path (parent directories)."""
    parts = os.path.normpath(csv_path).split(os.sep)
    # Path pattern: .../experiments/<map_name>/rerun_interval_sensitivity/...
    for i, part in enumerate(parts):
        if part == "rerun_interval_sensitivity" and i > 0:
            return parts[i - 1]
    return "unknown_map"


def plot(csv_path: str, save: bool = False):
    df = load(csv_path)
    output_dir = os.path.dirname(csv_path)

    map_name = infer_map_name(csv_path)

    arrival_rates = sorted(df["task_arrival_rate"].unique())
    ri_values = sorted(df["rerun_interval"].unique())
    ri_labels = [ri_display(r) for r in ri_values]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(f"rerun_interval Sensitivity — {map_name}", fontsize=13)

    # ── Plot 1: Throughput vs ri ──────────────────────────────────────────────
    ax = axes[0]
    tp = mean_by_ri(df, "throughput")
    for ar in arrival_rates:
        subset = tp[tp["task_arrival_rate"] == ar].sort_values("rerun_interval")
        ax.plot(range(len(ri_values)), subset["throughput"].values,
                marker="o", label=f"ar={ar:.4f}")

    ax.set_xticks(range(len(ri_values)))
    ax.set_xticklabels(ri_labels)
    ax.set_xlabel("rerun_interval")
    ax.set_ylabel("throughput (tasks/ts)")
    ax.set_title("Throughput vs rerun_interval")
    ax.legend(title="arrival rate", fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    # ── Plot 2: Interval-triggered calls vs ri ────────────────────────────────
    ax = axes[1]
    trig = mean_by_ri(df, "num_gcbba_runs_interval_triggered")
    for ar in arrival_rates:
        subset = trig[trig["task_arrival_rate"] == ar].sort_values("rerun_interval")
        ax.plot(range(len(ri_values)), subset["num_gcbba_runs_interval_triggered"].values,
                marker="o", label=f"ar={ar:.4f}")

    ax.set_xticks(range(len(ri_values)))
    ax.set_xticklabels(ri_labels)
    ax.set_xlabel("rerun_interval")
    ax.set_ylabel("allocation calls triggered by ri")
    ax.set_title("How often did ri actually fire?")
    ax.legend(title="arrival rate", fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()

    if save:
        out = os.path.join(output_dir, "ri_sensitivity.png")
        plt.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved: {out}")
    else:
        plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to summary.csv")
    parser.add_argument("--save", action="store_true", help="Save PNG instead of showing")
    args = parser.parse_args()
    plot(args.csv, save=args.save)
