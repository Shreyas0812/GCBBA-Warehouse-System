import argparse
import csv
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
import itertools
import json
import os
import sys
import traceback
from typing import List, Dict
import yaml as _yaml

from helper.machine_info import collect_machine_info
from helper.map_utils import calculate_average_service_time
from run_single_experiment import run_single_sensitivity_experiment
from SensitivityMetrics import SensitivityMetrics  # used for type hints and saving

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def get_experiment_configs(
    map_path: str = "",
    num_agents: int = 6,
    num_induct: int = 8,
    grid_w: int = 30,
    grid_h: int = 30,
) -> list:
    """
    Builds list of experiment configurations to run based on the selected mode and map parameters.
    - num_agents: number of agents in the map (used for scaling certain parameters).
    - num_induct: number of induct stations in the map (used for scaling certain parameters).
    - grid_w, grid_h: dimensions of the grid (used for scaling certain parameters).

    Parameters swept:
    - arrival_rates  : tasks per timestep per induct station
    - comm_ranges    : communication range (grid units)
    - rerun_interval : ONLY for dynamic GCBBA (static/cbba/sga use 999999)

    Arrival rates and comm ranges are derived analytically from map geometry
    """
    configs = []

    # ── Map-derived sweep anchors ──────────────────────────────────────────
    avg_service_time = calculate_average_service_time(map_path)  # in timesteps
    capacity = num_agents / (avg_service_time * num_induct)  # tasks/ts/station at full utilisation
    diagonal = (grid_w ** 2 + grid_h ** 2) ** 0.5


    seeds = [5, 42, 123, 456]

    capacity_fracs = [0.5, 1.0, 1.5, 2.0]  # Light → knee → overload → heavy
    arrival_rates = sorted(set(max(0.001, round(f * capacity, 4)) for f in capacity_fracs))

    range_fracs = [0.35] # 35% (knee) -- Does not affect Rerun Interval sensitivity
    comm_ranges   = sorted(set(max(3, round(f * diagonal))        for f in range_fracs))

    map_default_ri = round(2 * avg_service_time)  # Value used in main experiments
    rerun_intervals = sorted(set([10, 25, 50, 100, 200, map_default_ri, 999999]))  # 999999 = static (no reruns)

    STUCK_THRESHOLD = 15 # timesteps with no progress before we consider an agent stuck and trigger a replanning
    MAX_TIMESTEPS = max(1500, round(avg_service_time * 50))  # run for 50 full task cycles at knee 
    WARMUP_TIMESTEPS = max(200, round(avg_service_time * 5))  # warmup for 5 full task cycles
   
    QUEUE_MAX_DEPTH = 10 # max number of pending tasks to keep in the queue per station (beyond initial tasks). Older tasks are dropped on overflow.
    SS_INITIAL_TASKS = 2 * num_agents

    ALLOCATION_TIMEOUT_S = 10.0
    WALL_CLOCK_LIMIT_S = 600.0

    for ar, cr in itertools.product(arrival_rates, comm_ranges):
        
        for ri in rerun_intervals:
            configs.append({
                "config_name": f"lcba_dynamic_ar{ar:.4f}_cr{cr:.1f}_ri{ri}",
                "allocation_method": "gcbba",
                "path_planner": "bfs",
                "task_arrival_rate": ar,
                "initial_tasks": SS_INITIAL_TASKS,
                "queue_max_depth": QUEUE_MAX_DEPTH,
                "warmup_timesteps": WARMUP_TIMESTEPS,
                "comm_range": cr,
                "rerun_interval": ri,
                "stuck_threshold": STUCK_THRESHOLD,
                "seeds": seeds,
                "max_timesteps": MAX_TIMESTEPS,
                "allocation_timeout_s": ALLOCATION_TIMEOUT_S,
                "wall_clock_limit_s": WALL_CLOCK_LIMIT_S,
            })

    return configs


# ─────────────────────────────────────────────────────────────────
#  Metrics fields written to summary.csv
# ─────────────────────────────────────────────────────────────────

SENSITIVITY_FIELDS = [
    # Identity
    "run_id", "config_name", "seed", "rerun_interval", "task_arrival_rate", "comm_range",
    # Outcome
    "total_steps", "hit_timestep_ceiling", "hit_wall_clock_ceiling",
    # Primary — does ri help?
    "throughput", "avg_task_wait_time", "avg_queue_depth",
    "queue_saturation_fraction", "tasks_dropped_by_queue_cap",
    "steady_state_tasks_completed", "total_tasks_injected",
    # Secondary — cost of ri
    "num_gcbba_runs", "num_gcbba_runs_interval_triggered",
    "avg_gcbba_time_ms", "total_gcbba_time_ms",
    # Tertiary — interpretation
    "avg_idle_ratio", "task_balance_std",
    # Wall clock
    "wall_time_seconds",
]


# ─────────────────────────────────────────────────────────────────
#  Results saving
# ─────────────────────────────────────────────────────────────────

def _save_run_metrics(metrics: SensitivityMetrics, output_dir: str) -> None:
    """Save full metrics dataclass as JSON in a per-run subdirectory."""
    run_dir = os.path.join(output_dir, metrics.run_id)
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "metrics.json"), "w") as f:
        json.dump(asdict(metrics), f, indent=2, default=str)


def _save_summary_csv(all_metrics: List[SensitivityMetrics], output_dir: str) -> None:
    """Write focused summary CSV with only sensitivity-relevant fields."""
    summary_path = os.path.join(output_dir, "summary.csv")
    with open(summary_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SENSITIVITY_FIELDS)
        writer.writeheader()
        for m in all_metrics:
            writer.writerow({k: getattr(m, k) for k in SENSITIVITY_FIELDS})
    print(f"\nSummary CSV: {summary_path}  ({len(all_metrics)} runs)")


def _print_result(metrics: SensitivityMetrics, run_num: int, total_runs: int) -> None:
    ri_label = metrics.rerun_interval if metrics.rerun_interval < 999999 else "ri-static"
    print(
        f"  [DONE {run_num}/{total_runs}] "
        f"ri={ri_label} ar={metrics.task_arrival_rate:.4f} "
        f"→ throughput={metrics.throughput:.4f} "
        f"wait={metrics.avg_task_wait_time:.1f}ts "
        f"dropped={metrics.tasks_dropped_by_queue_cap}"
    )


# ─────────────────────────────────────────────────────────────────
#  Parallel worker (module-level so ProcessPoolExecutor can pickle it)
# ─────────────────────────────────────────────────────────────────

def _run_task(task: Dict):
    """
    Execute one (cfg, seed) experiment and save its per-run results.
    Returns (metrics, label) so the main process can aggregate and print progress.
    Must be a module-level function to be picklable by ProcessPoolExecutor.
    """
    metrics = run_single_sensitivity_experiment(
        task["config_path"],
        task["config_name"],
        task["task_arrival_rate"],
        task["queue_max_depth"],
        task["warmup_timesteps"],
        task["comm_range"],
        task["rerun_interval"],
        task["stuck_threshold"],
        task["seed"],
        task["max_timesteps"],
        allocation_method=task["allocation_method"],
        path_planner=task.get("path_planner", "bfs"),
        initial_tasks=task["initial_tasks"],
        allocation_timeout_s=task["allocation_timeout_s"],
        wall_clock_limit_s=task["wall_clock_limit_s"],
        max_plan_time=task["max_plan_time"],
    )
    return metrics, task["label"]
    
def main():
    parser = argparse.ArgumentParser(description="Thesis Experiment Sensitivity Runner used to choose the ri for the main experiments")

    parser.add_argument("--output", default=None, help="Override output directory")

    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "Number of parallel worker processes. "
            "1 = sequential (default). "
            "0 = use all CPU cores (os.cpu_count()). "
            "On a 16-core machine try --workers 16."
        ),
    )

    parser.add_argument(
        "--map",
        default="gridworld_warehouse_small",
        help=(
            "Config map name (without .yaml extension). "
            "File must exist in config/. "
            "Default: gridworld_warehouse_small"
        ),
    )
    args = parser.parse_args()

    map_name = args.map.replace(".yaml", "")
    map_path = os.path.join(PROJECT_ROOT, "config", f"{map_name}.yaml")
    if not os.path.exists(map_path):
        print(f"ERROR: Map not found: {map_path}")
        sys.exit(1)

    with open(map_path) as _f:
        _cfg = _yaml.safe_load(_f)
    _params = _cfg["create_gridworld_node"]["ros__parameters"]
    _map_num_agents = len(_params["agent_positions"]) // 4
    _map_num_induct  = len(_params["induct_stations"]) // 4
    _grid_w = _params.get("grid_width", 30)
    _grid_h = _params.get("grid_height", 30)
    _map_plan_time = max(200, _grid_w + _grid_h)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output or os.path.join(
        PROJECT_ROOT, "results", "experiments", map_name, "rerun_interval_sensitivity", timestamp
    )
    os.makedirs(output_dir, exist_ok=True)

    configs = get_experiment_configs(
        map_path=map_path,
        num_agents=_map_num_agents,
        num_induct=_map_num_induct,
        grid_w=_grid_w,
        grid_h=_grid_h
    )

    num_workers = args.workers if args.workers > 0 else os.cpu_count()
    total_runs = sum(len(cfg["seeds"]) for cfg in configs)

    print(f"\n{'='*70}")
    print(f"LCBA Experiments | map={map_name} | agents={_map_num_agents} | {total_runs} total runs | workers={num_workers}")
    print(f"Arrival rates:   {sorted(set(c['task_arrival_rate'] for c in configs))}")
    print(f"Comm ranges:     {sorted(set(c['comm_range'] for c in configs))}")
    print(f"Rerun intervals: {sorted(set(c['rerun_interval'] for c in configs if c['rerun_interval'] < 999999))} and 999999 (ri-static, no reruns)")
    print(f"Output:          {output_dir}")
    print(f"{'='*70}\n")

    # Save experiment metadata + machine info
    machine_info = collect_machine_info()
    with open(os.path.join(output_dir, "experiment_config.json"), "w") as f:
        json.dump(
            {
                "experiment": "LCBA Sensitivity Analysis",
                "map": map_name,
                "timestamp": timestamp,
                "total_runs": total_runs,
                "workers": num_workers,
                "machine": machine_info,
                "configs": configs,
            },
            f,
            indent=2,
        )

    # Build flattened list of (config, seed) pairs for execution
    tasks = []
    for cfg in configs:
        for seed in cfg["seeds"]:
            tasks.append({
                "config_path": map_path,
                "config_name": cfg["config_name"],
                "task_arrival_rate": cfg["task_arrival_rate"],
                "queue_max_depth": cfg["queue_max_depth"],
                "warmup_timesteps": cfg["warmup_timesteps"],
                "comm_range": cfg["comm_range"],
                "rerun_interval": cfg["rerun_interval"],
                "stuck_threshold": cfg["stuck_threshold"],
                "seed": seed,
                "max_timesteps": cfg["max_timesteps"],
                "allocation_method": cfg["allocation_method"],
                "initial_tasks": cfg["initial_tasks"],
                "allocation_timeout_s": cfg["allocation_timeout_s"],
                "wall_clock_limit_s": cfg["wall_clock_limit_s"],
                "max_plan_time": _map_plan_time,
                "output_dir": output_dir,
                "label": (
                    f"{cfg['config_name']} "
                    f"ar{cfg['task_arrival_rate']:.4f} "
                    f"cr{cfg['comm_range']:.1f} "
                    f"{cfg['rerun_interval'] if cfg['rerun_interval'] < 999999 else 'ri-static'} "
                    f"seed={seed}"
                )
            })

    all_metrics: List[SensitivityMetrics] = []

    if num_workers == 1:
        print("Running experiments sequentially...")
        for run_num, task in enumerate(tasks, 1):
            print(f"\n[RUN {run_num}/{total_runs}] {task['label']}")
            try:
                metrics, _ = _run_task(task)
                all_metrics.append(metrics)
                _save_run_metrics(metrics, output_dir)
                _print_result(metrics, run_num, total_runs)
            except Exception as e:
                print(f"ERROR in run {task['label']}: {e}")
                traceback.print_exc()
    else:
        completed = 0
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            future_to_task = {executor.submit(_run_task, task): task for task in tasks}
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                completed += 1
                try:
                    metrics, _ = future.result()
                    all_metrics.append(metrics)
                    _save_run_metrics(metrics, output_dir)
                    _print_result(metrics, completed, total_runs)
                except Exception as e:
                    print(f"ERROR in run {task['label']}: {e}")
                    traceback.print_exc()

    if all_metrics:
        _save_summary_csv(all_metrics, output_dir)

if __name__ == "__main__":
    main()