"""
plot_batch_results.py
=====================
Plots primary metrics from a completed batch experiment summary.csv.

Averages over seeds. Produces a 2x3 grid of subplots:
  1. Makespan vs Task Count       (completed runs only, at fixed comm_range)
  2. Task Completion Rate vs Task Count  (all runs, at fixed comm_range)
  3. Makespan vs Comm Range       (completed runs only, at fixed task_count)
  4. Allocation Time vs Task Count (all runs, at fixed comm_range)
  5. Agent Idle Ratio vs Task Count (all runs, at fixed comm_range)
  6. Deadlocks vs Task Count      (all runs, at fixed comm_range)

Usage:
    python experiments/plotting/plot_batch_results.py --csv path/to/summary.csv
    python experiments/plotting/plot_batch_results.py --csv path/to/summary.csv --save
    python experiments/plotting/plot_batch_results.py --csv path/to/summary.csv --comm-range 25
    python experiments/plotting/plot_batch_results.py --csv path/to/summary.csv --task-count 265
"""

import argparse
import os

import pandas as pd
import matplotlib.pyplot as plt

ALG_ORDER  = ["gcbba", "cbba", "dmchba", "sga"]
ALG_LABELS = {"gcbba": "GCBBA", "cbba": "CBBA", "dmchba": "DMCHBA", "sga": "SGA"}
ALG_COLORS = {"gcbba": "#1f77b4", "cbba": "#ff7f0e", "dmchba": "#2ca02c", "sga": "#d62728"}
ALG_MARKERS = {"gcbba": "o", "cbba": "s", "dmchba": "^", "sga": "D"}

DEFAULT_COMM_RANGE = 51
DEFAULT_TASK_COUNT = 151


def infer_map_name(csv_path: str) -> str:
    parts = os.path.normpath(csv_path).split(os.sep)
    for i, part in enumerate(parts):
        if part == "experiments" and i + 2 < len(parts):
            return parts[i + 1]
    return "unknown_map"


def load(csv_path: str):
    df = pd.read_csv(csv_path)
    batch = df[df["experiment_type"] == "batch"].copy()
    batch["completion_rate"] = batch["num_tasks_completed"] / batch["num_tasks_total"]
    return batch


def mean_over_seeds(df: pd.DataFrame, groupby: list, metric: str) -> pd.DataFrame:
    return df.groupby(groupby)[metric].mean().reset_index()


def plot_line(ax, agg, x_col, metric, algorithms, xlabel, ylabel, title):
    for alg in algorithms:
        subset = agg[agg["allocation_method"] == alg].sort_values(x_col)
        if subset.empty:
            continue
        ax.plot(subset[x_col], subset[metric],
                marker=ALG_MARKERS.get(alg, "o"), markersize=5,
                label=ALG_LABELS.get(alg, alg),
                color=ALG_COLORS.get(alg))
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)


def plot(csv_path: str, comm_range: float, task_count: int, save: bool = False):
    df = load(csv_path)
    if df.empty:
        print("No batch rows found in CSV.")
        return

    map_name   = infer_map_name(csv_path)
    output_dir = os.path.dirname(csv_path)
    algorithms = [a for a in ALG_ORDER if a in df["allocation_method"].unique()]

    # Resolve defaults if requested value not present
    available_crs = sorted(df["comm_range"].unique())
    available_tcs = sorted(df["initial_tasks"].unique())
    if comm_range not in available_crs:
        comm_range = available_crs[-1]
        print(f"Requested comm_range not found; using {comm_range}")
    if task_count not in available_tcs:
        task_count = available_tcs[len(available_tcs) // 2]
        print(f"Requested task_count not found; using {task_count}")

    at_cr   = df[df["comm_range"] == comm_range]
    at_cr_c = at_cr[at_cr["all_tasks_completed"] == True]
    at_tc   = df[df["initial_tasks"] == task_count]
    at_tc_c = at_tc[at_tc["all_tasks_completed"] == True]

    fig, axes = plt.subplots(2, 3, figsize=(18, 9))
    fig.suptitle(
        f"Batch Algorithm Comparison — {map_name}  "
        f"[cr={comm_range} for left/center cols | tc={task_count} for right col]",
        fontsize=13,
    )

    # ── 1. Makespan vs Task Count ─────────────────────────────────────────────
    ax = axes[0][0]
    if at_cr_c.empty:
        ax.text(0.5, 0.5, "No completed runs at this comm_range",
                ha="center", va="center", transform=ax.transAxes, fontsize=9)
        ax.set_title(f"Makespan vs Task Count  [cr={comm_range}]", fontsize=10)
    else:
        agg = mean_over_seeds(at_cr_c, ["allocation_method", "initial_tasks"], "makespan")
        plot_line(ax, agg, "initial_tasks", "makespan", algorithms,
                  "initial tasks", "makespan (timesteps)",
                  f"Makespan vs Task Count  [cr={comm_range}]")

    # ── 2. Task Completion Rate vs Task Count ─────────────────────────────────
    ax = axes[0][1]
    agg = mean_over_seeds(at_cr, ["allocation_method", "initial_tasks"], "completion_rate")
    plot_line(ax, agg, "initial_tasks", "completion_rate", algorithms,
              "initial tasks", "completion rate (fraction)",
              f"Completion Rate vs Task Count  [cr={comm_range}]")
    ax.set_ylim(0, 1.05)

    # ── 3. Makespan vs Comm Range ─────────────────────────────────────────────
    ax = axes[0][2]
    if at_tc_c.empty:
        ax.text(0.5, 0.5, "No completed runs at this task_count",
                ha="center", va="center", transform=ax.transAxes, fontsize=9)
        ax.set_title(f"Makespan vs Comm Range  [tc={task_count}]", fontsize=10)
    else:
        agg = mean_over_seeds(at_tc_c, ["allocation_method", "comm_range"], "makespan")
        plot_line(ax, agg, "comm_range", "makespan", algorithms,
                  "comm range", "makespan (timesteps)",
                  f"Makespan vs Comm Range  [tc={task_count}]")

    # ── 4. Allocation Time vs Task Count ──────────────────────────────────────
    ax = axes[1][0]
    agg = mean_over_seeds(at_cr, ["allocation_method", "initial_tasks"], "avg_allocation_time_ms")
    plot_line(ax, agg, "initial_tasks", "avg_allocation_time_ms", algorithms,
              "initial tasks", "avg allocation time (ms)",
              f"Allocation Time vs Task Count  [cr={comm_range}]")

    # ── 5. Agent Idle Ratio vs Task Count ─────────────────────────────────────
    ax = axes[1][1]
    agg = mean_over_seeds(at_cr, ["allocation_method", "initial_tasks"], "avg_idle_ratio")
    plot_line(ax, agg, "initial_tasks", "avg_idle_ratio", algorithms,
              "initial tasks", "avg idle ratio",
              f"Agent Idle Ratio vs Task Count  [cr={comm_range}]")

    # ── 6. Deadlocks vs Task Count ────────────────────────────────────────────
    ax = axes[1][2]
    agg = mean_over_seeds(at_cr, ["allocation_method", "initial_tasks"], "num_deadlocks")
    plot_line(ax, agg, "initial_tasks", "num_deadlocks", algorithms,
              "initial tasks", "num deadlocks",
              f"Deadlocks vs Task Count  [cr={comm_range}]")
    ax.annotate(
        "Note: deadlock counts are partially planner-driven (CA* conflict\n"
        "resolution); inter-algorithm differences reflect task density.",
        xy=(0.01, 0.01), xycoords="axes fraction", fontsize=6.5,
        color="gray", va="bottom",
    )

    plt.tight_layout()

    if save:
        out = os.path.join(output_dir, f"batch_results_cr{int(comm_range)}_tc{task_count}.png")
        plt.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved: {out}")
    else:
        plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv",        required=True,               help="Path to summary.csv")
    parser.add_argument("--save",       action="store_true",         help="Save PNG instead of showing")
    parser.add_argument("--comm-range", type=float, default=DEFAULT_COMM_RANGE,
                        help=f"Comm range for task-count plots (default: {DEFAULT_COMM_RANGE})")
    parser.add_argument("--task-count", type=int,   default=DEFAULT_TASK_COUNT,
                        help=f"Task count for comm-range plot (default: {DEFAULT_TASK_COUNT})")
    args = parser.parse_args()
    plot(args.csv, comm_range=args.comm_range, task_count=args.task_count, save=args.save)
