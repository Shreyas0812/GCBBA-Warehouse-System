"""
plot_batch_results.py
=====================
Comprehensive plotting for batch experiment summary.csv files.

Produces a 2x5 dashboard:
    1. Makespan vs Task Count (completed runs only, fixed comm_range)
    2. Completion Rate vs Task Count (all runs, fixed comm_range)
    3. Makespan vs Comm Range (completed runs only, fixed task_count)
    4. Allocation Time vs Task Count (all runs, fixed comm_range)
    5. Timeout Rate vs Task Count (all runs, fixed comm_range)
    6. Wall Time vs Task Count (all runs, fixed comm_range)
    7. Deadlocks vs Task Count (all runs, fixed comm_range)
    8. Idle Ratio vs Task Count (all runs, fixed comm_range)
    9. Task Balance Std vs Task Count (all runs, fixed comm_range)
   10. Timeout Rate vs Comm Range (all runs, fixed task_count)

Usage:
        python experiments/plotting/plot_batch_results.py --csv path/to/summary.csv
        python experiments/plotting/plot_batch_results.py --csv path/to/summary.csv --save
        python experiments/plotting/plot_batch_results.py --csv path/to/summary.csv --comm-range 25
        python experiments/plotting/plot_batch_results.py --csv path/to/summary.csv --task-count 265
        python experiments/plotting/plot_batch_results.py --csv path/to/summary.csv --include-wall-clock-timeouts
"""

import argparse
import os
import sys
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt

ALG_ORDER  = ["gcbba", "cbba", "dmchba", "sga"]
ALG_LABELS = {"gcbba": "LCBA", "cbba": "CBBA", "dmchba": "DMCHBA", "sga": "SGA"}
ALG_COLORS = {"gcbba": "#1f77b4", "cbba": "#ff7f0e", "dmchba": "#2ca02c", "sga": "#d62728"}
ALG_MARKERS = {"gcbba": "o", "cbba": "s", "dmchba": "^", "sga": "D"}

DEFAULT_COMM_RANGE = 51
DEFAULT_TASK_COUNT = 151
DEFAULT_MIN_SEEDS = 2


def infer_map_name(csv_path: str) -> str:
    parts = os.path.normpath(csv_path).split(os.sep)
    for i, part in enumerate(parts):
        if part == "experiments" and i + 2 < len(parts):
            return parts[i + 1]
    return "unknown_map"


def infer_run_timestamp(csv_path: str) -> str:
    parts = os.path.normpath(csv_path).split(os.sep)
    for i, part in enumerate(parts):
        if part == "experiments" and i + 2 < len(parts):
            return parts[i + 2]
    return os.path.basename(os.path.dirname(csv_path))


def repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def default_output_root(csv_path: str, leaf_folder: str) -> str:
    return os.path.join(
        os.path.dirname(csv_path),
        leaf_folder,
    )


def load(csv_path: str, include_wall_clock_timeouts: bool):
    df = pd.read_csv(csv_path)
    batch = df[df["experiment_type"] == "batch"].copy()
    # Compute timeout_rate on full data BEFORE filtering so subplots 5/10 see real values
    batch["timeout_rate"] = batch["hit_wall_clock_ceiling"].astype(float)
    denom = batch["num_tasks_total"].replace(0, pd.NA)
    batch["completion_rate"] = batch["num_tasks_completed"] / denom

    batch_full = batch.copy()  # used only for timeout_rate aggregations
    if not include_wall_clock_timeouts:
        batch = batch[~batch["hit_wall_clock_ceiling"]].copy()
    return batch, batch_full


def mean_over_seeds(df: pd.DataFrame, groupby: list, metric: str, min_seeds: int) -> pd.DataFrame:
    grp = df.groupby(groupby)
    counts = grp[metric].count().reset_index(name="_n")
    means = grp[metric].mean().reset_index()
    merged = means.merge(counts, on=groupby)
    return merged[merged["_n"] >= min_seeds].drop(columns="_n")


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


def _closest_numeric(requested, available_values):
    if not available_values:
        return requested
    return min(available_values, key=lambda v: abs(float(v) - float(requested)))


def _fmt_num_for_name(v: float) -> str:
    s = f"{float(v):g}"
    return s.replace(".", "p")


def write_run_manifest(output_dir: str, command_text: str, metadata: dict) -> None:
    os.makedirs(output_dir, exist_ok=True)
    manifest_path = os.path.join(output_dir, "run_manifest.txt")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write("Batch Plot Run Manifest\n")
        f.write("=======================\n")
        f.write(f"timestamp: {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"command: {command_text}\n")
        for key in sorted(metadata.keys()):
            f.write(f"{key}: {metadata[key]}\n")


def plot(
    csv_path: str,
    comm_range: float,
    task_count: int,
    min_seeds: int,
    include_wall_clock_timeouts: bool,
    save: bool = False,
    separate: bool = False,
    output_dir: str = None,
    command_text: str = "",
):
    df, df_full = load(csv_path, include_wall_clock_timeouts=include_wall_clock_timeouts)
    if df_full.empty:
        print("No batch rows found in CSV.")
        return
    if df.empty and not include_wall_clock_timeouts:
        print("All batch rows hit wall-clock timeout; using full data for timeout plots only.")

    map_name   = infer_map_name(csv_path)
    if output_dir is None:
        output_dir = default_output_root(csv_path, "batch_results")
    os.makedirs(output_dir, exist_ok=True)
    write_run_manifest(
        output_dir,
        command_text,
        {
            "csv": csv_path,
            "comm_range": comm_range,
            "task_count": task_count,
            "min_seeds": min_seeds,
            "include_wall_clock_timeouts": include_wall_clock_timeouts,
            "save_combined": save,
            "save_separate": separate,
            "mode": "single",
        },
    )
    algorithms = [a for a in ALG_ORDER if a in df_full["allocation_method"].unique()]

    # Resolve defaults if requested value not present
    available_crs = sorted(df_full["comm_range"].unique())
    available_tcs = sorted(df_full["initial_tasks"].unique())
    if comm_range not in available_crs:
        comm_range = _closest_numeric(comm_range, available_crs)
        print(f"Requested comm_range not found; using nearest value {comm_range}")
    if task_count not in available_tcs:
        task_count = int(_closest_numeric(task_count, available_tcs))
        print(f"Requested task_count not found; using nearest value {task_count}")

    at_cr      = df[df["comm_range"] == comm_range]
    at_cr_c    = at_cr[at_cr["all_tasks_completed"]]
    at_tc      = df[df["initial_tasks"] == task_count]
    at_tc_c    = at_tc[at_tc["all_tasks_completed"]]
    # Full (pre-filter) slices for timeout_rate subplots
    at_cr_full = df_full[df_full["comm_range"] == comm_range]
    at_tc_full = df_full[df_full["initial_tasks"] == task_count]

    fig, axes = plt.subplots(2, 5, figsize=(30, 10))
    fig.suptitle(
        f"Batch Algorithm Comparison — {map_name}  "
        f"[cr={comm_range} task-count views | tc={task_count} comm-range view]",
        fontsize=13,
    )

    # ── 1. Makespan vs Task Count ─────────────────────────────────────────────
    ax = axes[0][0]
    if at_cr_c.empty:
        ax.text(0.5, 0.5, "No completed runs at this comm_range",
                ha="center", va="center", transform=ax.transAxes, fontsize=9)
        ax.set_title(f"Makespan vs Task Count  [cr={comm_range}]", fontsize=10)
    else:
        agg = mean_over_seeds(at_cr_c, ["allocation_method", "initial_tasks"], "makespan", min_seeds)
        plot_line(ax, agg, "initial_tasks", "makespan", algorithms,
                  "initial tasks", "makespan (timesteps)",
                  f"Makespan vs Task Count  [cr={comm_range}]")

    # ── 2. Task Completion Rate vs Task Count ─────────────────────────────────
    ax = axes[0][1]
    agg = mean_over_seeds(at_cr, ["allocation_method", "initial_tasks"], "completion_rate", min_seeds)
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
        agg = mean_over_seeds(at_tc_c, ["allocation_method", "comm_range"], "makespan", min_seeds)
        plot_line(ax, agg, "comm_range", "makespan", algorithms,
                  "comm range", "makespan (timesteps)",
                  f"Makespan vs Comm Range  [tc={task_count}]")

    # ── 4. Allocation Time vs Task Count ──────────────────────────────────────
    ax = axes[0][3]
    agg = mean_over_seeds(at_cr, ["allocation_method", "initial_tasks"], "avg_allocation_time_ms", min_seeds)
    plot_line(ax, agg, "initial_tasks", "avg_allocation_time_ms", algorithms,
              "initial tasks", "avg allocation time (ms)",
              f"Allocation Time vs Task Count  [cr={comm_range}]")

    # ── 5. Timeout Rate vs Task Count ────────────────────────────────────────
    ax = axes[0][4]
    agg = mean_over_seeds(at_cr_full, ["allocation_method", "initial_tasks"], "timeout_rate", min_seeds)
    plot_line(ax, agg, "initial_tasks", "timeout_rate", algorithms,
              "initial tasks", "timeout rate",
              f"Timeout Rate vs Task Count  [cr={comm_range}]")
    ax.set_ylim(0, 1.05)

    # ── 6. Wall Time vs Task Count ─────────────────────────────────────────────
    ax = axes[1][0]
    agg = mean_over_seeds(at_cr, ["allocation_method", "initial_tasks"], "wall_time_seconds", min_seeds)
    plot_line(ax, agg, "initial_tasks", "wall_time_seconds", algorithms,
              "initial tasks", "wall time (s)",
              f"Wall Time vs Task Count  [cr={comm_range}]")

    # ── 7. Deadlocks vs Task Count ────────────────────────────────────────────
    ax = axes[1][1]
    agg = mean_over_seeds(at_cr, ["allocation_method", "initial_tasks"], "num_deadlocks", min_seeds)
    plot_line(ax, agg, "initial_tasks", "num_deadlocks", algorithms,
              "initial tasks", "num deadlocks",
              f"Deadlocks vs Task Count  [cr={comm_range}]")

    # ── 8. Agent Idle Ratio vs Task Count ─────────────────────────────────────
    ax = axes[1][2]
    agg = mean_over_seeds(at_cr, ["allocation_method", "initial_tasks"], "avg_idle_ratio", min_seeds)
    plot_line(ax, agg, "initial_tasks", "avg_idle_ratio", algorithms,
              "initial tasks", "avg idle ratio",
              f"Agent Idle Ratio vs Task Count  [cr={comm_range}]")

    # ── 9. Task Balance Std vs Task Count ─────────────────────────────────────
    ax = axes[1][3]
    agg = mean_over_seeds(at_cr, ["allocation_method", "initial_tasks"], "task_balance_std", min_seeds)
    plot_line(ax, agg, "initial_tasks", "task_balance_std", algorithms,
              "initial tasks", "task balance std",
              f"Task Balance Std vs Task Count  [cr={comm_range}]")

    # ── 10. Timeout Rate vs Comm Range ───────────────────────────────────────
    ax = axes[1][4]
    agg = mean_over_seeds(at_tc_full, ["allocation_method", "comm_range"], "timeout_rate", min_seeds)
    plot_line(ax, agg, "comm_range", "timeout_rate", algorithms,
              "comm range", "timeout rate",
              f"Timeout Rate vs Comm Range  [tc={task_count}]")
    ax.set_ylim(0, 1.05)

    if not include_wall_clock_timeouts:
        fig.text(
            0.01,
            0.01,
            "Quality/cost subplots exclude timeout runs; timeout-rate subplots use full batch data.",
            fontsize=8,
            color="gray",
            va="bottom",
        )

    plt.tight_layout()

    cr_tag = _fmt_num_for_name(comm_range)
    suffix = "_incl_timeouts" if include_wall_clock_timeouts else ""

    if save:
        out = os.path.join(output_dir, f"batch_results_cr{cr_tag}_tc{task_count}{suffix}.png")
        plt.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved: {out}")

    if separate:
        slugs = [
            "makespan_vs_tc", "completion_rate_vs_tc", "makespan_vs_cr",
            "alloc_time_vs_tc", "timeout_rate_vs_tc",
            "wall_time_vs_tc", "deadlocks_vs_tc", "idle_ratio_vs_tc",
            "task_balance_vs_tc", "timeout_rate_vs_cr",
        ]
        for src_ax, slug in zip(axes.flat, slugs):
            single_fig, single_ax = plt.subplots(1, 1, figsize=(8, 5))

            # Recreate plotted lines so each subplot is exported as a clean standalone figure.
            for line in src_ax.get_lines():
                single_ax.plot(
                    line.get_xdata(),
                    line.get_ydata(),
                    linestyle=line.get_linestyle(),
                    marker=line.get_marker(),
                    markersize=line.get_markersize(),
                    color=line.get_color(),
                    label=line.get_label(),
                )

            for txt in src_ax.texts:
                single_ax.text(
                    txt.get_position()[0],
                    txt.get_position()[1],
                    txt.get_text(),
                    transform=txt.get_transform(),
                    ha=txt.get_ha(),
                    va=txt.get_va(),
                    fontsize=txt.get_fontsize(),
                    color=txt.get_color(),
                )

            single_ax.set_title(src_ax.get_title(), fontsize=10)
            single_ax.set_xlabel(src_ax.get_xlabel(), fontsize=9)
            single_ax.set_ylabel(src_ax.get_ylabel(), fontsize=9)
            single_ax.grid(axis="y", alpha=0.3)

            if src_ax.get_legend() is not None and src_ax.get_lines():
                single_ax.legend(fontsize=8)

            y0, y1 = src_ax.get_ylim()
            single_ax.set_ylim(y0, y1)

            single_fig.tight_layout()
            out = os.path.join(output_dir, f"batch_{slug}_cr{cr_tag}_tc{task_count}{suffix}.png")
            single_fig.savefig(out, dpi=150, bbox_inches="tight")
            plt.close(single_fig)
            print(f"Saved: {out}")

    if not save and not separate:
        plt.show()

    plt.close(fig)


def run_sweeps(
    csv_path: str,
    comm_range: float,
    task_count: int,
    min_seeds: int,
    include_wall_clock_timeouts: bool,
    save: bool,
    separate: bool,
    output_root: str,
    sweep_task_counts: bool,
    sweep_comm_ranges: bool,
    command_text: str,
):
    df, df_full = load(csv_path, include_wall_clock_timeouts=include_wall_clock_timeouts)
    if df_full.empty:
        print("No batch rows found in CSV.")
        return

    if output_root is None:
        output_root = default_output_root(csv_path, "batch_results")
    os.makedirs(output_root, exist_ok=True)
    write_run_manifest(
        output_root,
        command_text,
        {
            "csv": csv_path,
            "fixed_comm_range": comm_range,
            "fixed_task_count": task_count,
            "min_seeds": min_seeds,
            "include_wall_clock_timeouts": include_wall_clock_timeouts,
            "save_combined": save,
            "save_separate": separate,
            "sweep_task_counts": sweep_task_counts,
            "sweep_comm_ranges": sweep_comm_ranges,
            "mode": "sweep",
        },
    )

    if sweep_task_counts:
        for tc in sorted(df_full["initial_tasks"].unique()):
            out_dir = os.path.join(output_root, "by_task_count", f"tc_{int(tc)}")
            print(f"Generating task-count slice in {out_dir}")
            plot(
                csv_path=csv_path,
                comm_range=comm_range,
                task_count=int(tc),
                min_seeds=min_seeds,
                include_wall_clock_timeouts=include_wall_clock_timeouts,
                save=save,
                separate=separate,
                output_dir=out_dir,
                command_text=command_text,
            )

    if sweep_comm_ranges:
        for cr in sorted(df_full["comm_range"].unique()):
            out_dir = os.path.join(output_root, "by_comm_range", f"cr_{_fmt_num_for_name(cr)}")
            print(f"Generating comm-range slice in {out_dir}")
            plot(
                csv_path=csv_path,
                comm_range=float(cr),
                task_count=task_count,
                min_seeds=min_seeds,
                include_wall_clock_timeouts=include_wall_clock_timeouts,
                save=save,
                separate=separate,
                output_dir=out_dir,
                command_text=command_text,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv",        required=True,               help="Path to summary.csv")
    parser.add_argument("--save",       action="store_true",         help="Save combined PNG")
    parser.add_argument("--separate",   action="store_true",         help="Save each subplot as its own PNG")
    parser.add_argument("--output-root", type=str, default=None,
                        help="Base output directory for saved files (default: same folder as CSV)")
    parser.add_argument("--sweep-task-counts", action="store_true",
                        help="Generate outputs for every task count into by_task_count/ folders")
    parser.add_argument("--sweep-comm-ranges", action="store_true",
                        help="Generate outputs for every comm range into by_comm_range/ folders")
    parser.add_argument("--comm-range", type=float, default=DEFAULT_COMM_RANGE,
                        help=f"Comm range for task-count plots (default: {DEFAULT_COMM_RANGE})")
    parser.add_argument("--task-count", type=int,   default=DEFAULT_TASK_COUNT,
                        help=f"Task count for comm-range plot (default: {DEFAULT_TASK_COUNT})")
    parser.add_argument("--min-seeds", type=int, default=DEFAULT_MIN_SEEDS,
                        help=f"Minimum seeds required to show a point (default: {DEFAULT_MIN_SEEDS})")
    parser.add_argument("--include-wall-clock-timeouts", action="store_true",
                        help="Include runs that hit wall-clock ceiling in aggregates")
    args = parser.parse_args()
    command_text = "python " + " ".join(sys.argv)

    if args.sweep_task_counts or args.sweep_comm_ranges:
        run_sweeps(
            csv_path=args.csv,
            comm_range=args.comm_range,
            task_count=args.task_count,
            min_seeds=args.min_seeds,
            include_wall_clock_timeouts=args.include_wall_clock_timeouts,
            save=args.save,
            separate=args.separate,
            output_root=args.output_root,
            sweep_task_counts=args.sweep_task_counts,
            sweep_comm_ranges=args.sweep_comm_ranges,
            command_text=command_text,
        )
    else:
        plot(
            args.csv,
            comm_range=args.comm_range,
            task_count=args.task_count,
            min_seeds=args.min_seeds,
            include_wall_clock_timeouts=args.include_wall_clock_timeouts,
            save=args.save,
            separate=args.separate,
            output_dir=args.output_root,
            command_text=command_text,
        )
