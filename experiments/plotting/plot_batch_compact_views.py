"""
plot_batch_compact_views.py
===========================
Compact alternatives to many batch slice plots.

This script summarizes a batch run with a small number of figures:
1. Heatmaps per metric, one subplot per algorithm.
2. Critical-load curve: max task count that still achieves a completion
   threshold, plotted against comm_range.
3. Tradeoff scatter: completion rate vs wall time.

Outputs are written directly to:
    results/experiments/<map_name>/<timestamp>/batch_results/compact_views/

Usage:
    python experiments/plotting/plot_batch_compact_views.py --csv path/to/summary.csv --all --save
    python experiments/plotting/plot_batch_compact_views.py --csv path/to/summary.csv --heatmaps --save
    python experiments/plotting/plot_batch_compact_views.py --csv path/to/summary.csv --capacity --save
    python experiments/plotting/plot_batch_compact_views.py --csv path/to/summary.csv --tradeoff --save
"""

import argparse
import os

import matplotlib.pyplot as plt
import pandas as pd

ALG_ORDER = ["gcbba", "cbba", "dmchba", "sga"]
ALG_LABELS = {"gcbba": "LCBA", "cbba": "CBBA", "dmchba": "DMCHBA", "sga": "SGA"}
ALG_COLORS = {"gcbba": "#1f77b4", "cbba": "#ff7f0e", "dmchba": "#2ca02c", "sga": "#d62728"}

MIN_SEEDS_DEFAULT = 2

HEATMAP_METRICS = [
    ("completion_rate", "Completion Rate"),
    ("timeout_rate", "Timeout Rate"),
    ("makespan_completed", "Makespan (completed runs only)"),
    ("wall_time_seconds", "Wall Time (s)"),
]


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


def default_output_root(csv_path: str) -> str:
    return os.path.join(
        os.path.dirname(csv_path),
        "batch_results",
        "compact_views",
    )


def load_batch(csv_path: str, include_wall_clock_timeouts: bool) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df = df[df["experiment_type"] == "batch"].copy()
    if df.empty:
        return df

    denom = df["num_tasks_total"].replace(0, pd.NA)
    df["completion_rate"] = df["num_tasks_completed"] / denom
    df["timeout_rate"] = df["hit_wall_clock_ceiling"].astype(float)
    df["makespan_completed"] = df["makespan"].where(df["all_tasks_completed"], pd.NA)

    if not include_wall_clock_timeouts:
        df = df[~df["hit_wall_clock_ceiling"]].copy()

    return df


def mean_with_min_seeds(df: pd.DataFrame, keys: list, metric: str, min_seeds: int) -> pd.DataFrame:
    grp = df.groupby(keys)
    counts = grp[metric].count().reset_index(name="_n")
    means = grp[metric].mean().reset_index()
    out = means.merge(counts, on=keys)
    return out[out["_n"] >= min_seeds].drop(columns="_n")


def write_run_manifest(output_dir: str, command_text: str, metadata: dict) -> None:
    os.makedirs(output_dir, exist_ok=True)
    manifest_path = os.path.join(output_dir, "run_manifest.txt")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write("Batch Plot Run Manifest\n")
        f.write("=======================\n")
        f.write(f"command: {command_text}\n")
        for key in sorted(metadata.keys()):
            f.write(f"{key}: {metadata[key]}\n")


def save_or_show(fig, out_path: str, save: bool):
    fig.tight_layout()
    if save:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=160, bbox_inches="tight")
        print(f"Saved: {out_path}")
        plt.close(fig)
    else:
        plt.show()


def plot_heatmaps(df: pd.DataFrame, metric: str, metric_label: str, out_dir: str, map_name: str, save: bool, min_seeds: int):
    agg = mean_with_min_seeds(
        df,
        ["allocation_method", "initial_tasks", "comm_range"],
        metric,
        min_seeds,
    )

    algs = [a for a in ALG_ORDER if a in agg["allocation_method"].unique()]
    if not algs:
        print(f"No data for heatmap metric: {metric}")
        return

    fig, axes = plt.subplots(2, 2, figsize=(12, 9), squeeze=False)
    fig.suptitle(f"{metric_label} Heatmaps - {map_name}", fontsize=13)

    for idx in range(4):
        ax = axes[idx // 2][idx % 2]
        if idx >= len(algs):
            ax.axis("off")
            continue

        alg = algs[idx]
        sub = agg[agg["allocation_method"] == alg]
        piv = sub.pivot(index="initial_tasks", columns="comm_range", values=metric).sort_index().sort_index(axis=1)
        if piv.empty:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(ALG_LABELS.get(alg, alg))
            ax.axis("off")
            continue

        im = ax.imshow(piv.values, aspect="auto", origin="lower")
        ax.set_title(ALG_LABELS.get(alg, alg), fontsize=10)
        ax.set_xlabel("comm range", fontsize=9)
        ax.set_ylabel("initial tasks", fontsize=9)
        ax.set_xticks(range(len(piv.columns)))
        ax.set_xticklabels([str(c) for c in piv.columns], fontsize=8)
        ax.set_yticks(range(len(piv.index)))
        ax.set_yticklabels([str(r) for r in piv.index], fontsize=8)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    out = os.path.join(out_dir, f"compact_heatmap_{metric}.png")
    save_or_show(fig, out, save)


def plot_capacity_curve(df: pd.DataFrame, out_dir: str, map_name: str, save: bool, min_seeds: int, completion_threshold: float):
    agg = mean_with_min_seeds(
        df,
        ["allocation_method", "comm_range", "initial_tasks"],
        "completion_rate",
        min_seeds,
    )
    if agg.empty:
        print("No data for capacity curve.")
        return

    rows = []
    for (alg, cr), sub in agg.groupby(["allocation_method", "comm_range"]):
        ok = sub[sub["completion_rate"] >= completion_threshold]
        max_tc = ok["initial_tasks"].max() if not ok.empty else 0
        rows.append({"allocation_method": alg, "comm_range": cr, "max_completed_task_count": max_tc})

    cap = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(8, 5))
    for alg in [a for a in ALG_ORDER if a in cap["allocation_method"].unique()]:
        sub = cap[cap["allocation_method"] == alg].sort_values("comm_range")
        ax.plot(
            sub["comm_range"],
            sub["max_completed_task_count"],
            marker="o",
            label=ALG_LABELS.get(alg, alg),
            color=ALG_COLORS.get(alg),
        )

    ax.set_title(f"Critical Load vs Comm Range - {map_name}", fontsize=12)
    ax.set_xlabel("comm range")
    ax.set_ylabel(f"max task count with completion >= {completion_threshold:.2f}")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()

    out = os.path.join(out_dir, "compact_capacity_curve.png")
    save_or_show(fig, out, save)


def plot_tradeoff(df: pd.DataFrame, out_dir: str, map_name: str, save: bool, min_seeds: int):
    comp = mean_with_min_seeds(
        df,
        ["allocation_method", "initial_tasks", "comm_range"],
        "completion_rate",
        min_seeds,
    )
    wall = mean_with_min_seeds(
        df,
        ["allocation_method", "initial_tasks", "comm_range"],
        "wall_time_seconds",
        min_seeds,
    )
    merged = comp.merge(
        wall,
        on=["allocation_method", "initial_tasks", "comm_range"],
        suffixes=("_completion", "_wall"),
    )
    if merged.empty:
        print("No data for tradeoff plot.")
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    for alg in [a for a in ALG_ORDER if a in merged["allocation_method"].unique()]:
        sub = merged[merged["allocation_method"] == alg]
        ax.scatter(
            sub["wall_time_seconds"],
            sub["completion_rate"],
            s=45,
            alpha=0.8,
            label=ALG_LABELS.get(alg, alg),
            color=ALG_COLORS.get(alg),
        )

    ax.set_title(f"Completion vs Wall Time Tradeoff - {map_name}", fontsize=12)
    ax.set_xlabel("wall time (s)")
    ax.set_ylabel("completion rate")
    ax.set_ylim(0, 1.05)
    ax.grid(alpha=0.3)
    ax.legend()

    out = os.path.join(out_dir, "compact_tradeoff.png")
    save_or_show(fig, out, save)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to summary.csv")
    parser.add_argument("--save", action="store_true", help="Save PNGs instead of showing")
    parser.add_argument("--output-dir", default=None, help="Output folder (default: results/experiments/<map>/<timestamp>/batch_results/compact_views)")
    parser.add_argument("--min-seeds", type=int, default=MIN_SEEDS_DEFAULT)
    parser.add_argument("--include-wall-clock-timeouts", action="store_true")
    parser.add_argument("--completion-threshold", type=float, default=0.95)

    parser.add_argument("--all", action="store_true", help="Generate all compact views")
    parser.add_argument("--heatmaps", action="store_true")
    parser.add_argument("--capacity", action="store_true")
    parser.add_argument("--tradeoff", action="store_true")

    args = parser.parse_args()

    df = load_batch(args.csv, include_wall_clock_timeouts=args.include_wall_clock_timeouts)
    if df.empty:
        print("No batch rows found after filtering.")
        return

    map_name = infer_map_name(args.csv)
    ts = infer_run_timestamp(args.csv)
    out_dir = args.output_dir or default_output_root(args.csv)
    os.makedirs(out_dir, exist_ok=True)

    write_run_manifest(
        out_dir,
        "python " + " ".join(os.sys.argv),
        {
            "csv": args.csv,
            "map_name": map_name,
            "timestamp": ts,
            "min_seeds": args.min_seeds,
            "include_wall_clock_timeouts": args.include_wall_clock_timeouts,
            "completion_threshold": args.completion_threshold,
            "mode": "compact",
            "save": args.save,
        },
    )

    do_all = args.all or not (args.heatmaps or args.capacity or args.tradeoff)

    if do_all or args.heatmaps:
        for metric, label in HEATMAP_METRICS:
            plot_heatmaps(df, metric, label, out_dir, map_name, args.save, args.min_seeds)

    if do_all or args.capacity:
        plot_capacity_curve(df, out_dir, map_name, args.save, args.min_seeds, args.completion_threshold)

    if do_all or args.tradeoff:
        plot_tradeoff(df, out_dir, map_name, args.save, args.min_seeds)


if __name__ == "__main__":
    main()