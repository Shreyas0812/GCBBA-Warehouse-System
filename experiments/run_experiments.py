"""
Experiment Runner:

Usage:
  python run_experiments.py --mode quick    # ~8 runs, verify pipeline
  python run_experiments.py --mode full     # ~324 runs, thesis data (SS: 216, Batch: 108)
"""

import argparse
import csv
import json
import os
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
import itertools
from typing import List, Dict
import yaml as yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from helper.machine_info import collect_machine_info
from helper.map_utils import calculate_average_service_time
from Metrics import RunMetrics
from run_single_experiment import run_single_steady_state_experiment, run_single_batch_experiment

def get_experiment_configs(
    mode: str = 'full',
    config:str = 'all',
    num_agents: int = 6,
    num_induct: int = 8,
    grid_w: int = 30,
    grid_h: int = 30,
    map_path: str = None,
) -> List[Dict]:
    """
    Builds list of experiment configurations to run based on the selected mode and map parameters. 
     - mode: 'quick' to check functionality. otherwise, 'full' for comprehensive sweep (default).
     - num_agents: number of agents in the map (used for scaling certain parameters).
     - num_induct: number of induct stations in the map (used for scaling certain parameters).
     - grid_w, grid_h: dimensions of the grid (used for scaling certain parameters).

     Parameters swept:
      - ss_arrival_rates  : tasks per timestep per induct station
      - comm_ranges    : communication range (grid units)

      Arrival rates and comm ranges are derived analytically from map geometry
    """
    # Define constants - independent of the map but common across experiments
    STUCK_THRESHOLD = 15
    QUEUE_MAX_DEPTH = 10
    WARMUP_TIMESTEPS = 300
    ALLOCATION_TIMEOUT_S = 10.0
    WALL_CLOCK_LIMIT_S = 600.0

    SS_MAX_TIMESTEPS = 1500
    SS_INITIAL_TASKS = 2 * num_agents
    BATCH_MAX_TIMESTEPS = 3000

    configs = []

    # ── Map-derived sweep anchors ──────────────────────────────────────────
    diagonal = (grid_w ** 2 + grid_h ** 2) ** 0.5
    avg_service_time = calculate_average_service_time(map_path) if map_path else (grid_w + grid_h) / 2
    
    RERUN_INTERVAL = round(2 * avg_service_time)
    
    # Steady-state capacity: max arrival rate that keeps the system stable (tasks arrive at same rate they can be completed).
    _ss_capacity = num_agents / (avg_service_time * num_induct)

    # Batch capacity: max tasks all agents could complete before BATCH_MAX_TIMESTEPS.
    # Used as the anchor for the batch task count sweep (unlike steady-state which uses arrival capacity).
    _batch_capacity = round(num_agents * BATCH_MAX_TIMESTEPS / avg_service_time)

    if mode == "quick":
        seeds = [42]
        # One sparse range (35% diagonal) and one full-connectivity range
        range_fracs = [0.35, 1.2]
        # Knee (1×) and a heavy-load point (2×) only
        ss_capacity_fracs = [1.0, 2.0]

        batch_fracs = [0.2, 1.0]  # 20% of batch capacity and full batch capacity

    else:  # full
        seeds = [42, 123, 456]
        # 6 points spanning near-disconnected to full-connectivity
        range_fracs = [0.05, 0.1, 0.2, 0.35, 0.6, 1.2]
        # 10 points from 25% to 300% of ss capacity
        ss_capacity_fracs = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0]
        
        batch_fracs = [0.05, 0.1, 0.2, 0.4, 0.7, 1.0]

    comm_ranges = sorted(set(
        max(3, round(f * diagonal)) for f in range_fracs
    ))

    ss_arrival_rates = sorted(set(
        max(0.001, round(f * _ss_capacity, 4)) for f in ss_capacity_fracs
    ))

    batch_task_counts = sorted(set(
        max(num_agents, round(f * _batch_capacity)) for f in batch_fracs
    ))

    METHODS = ["gcbba", "cbba", "sga"]

    if config in ("all", "ss_only"):
        for method, ar, cr in itertools.product(METHODS, ss_arrival_rates, comm_ranges):
            configs.append({
                "config_name": f"{method}_ss_ar{ar:.4f}_cr{cr:.1f}",
                "allocation_method": method,
                "experiment_type": "steady_state",
                "task_arrival_rate": ar,
                "comm_range": cr,
                "initial_tasks": SS_INITIAL_TASKS,
                "rerun_interval": RERUN_INTERVAL,
                "max_timesteps": SS_MAX_TIMESTEPS,
                "warmup_timesteps": WARMUP_TIMESTEPS,
                "stuck_threshold": STUCK_THRESHOLD,
                "queue_max_depth": QUEUE_MAX_DEPTH,
                "allocation_timeout_s": ALLOCATION_TIMEOUT_S,
                "wall_clock_limit_s": WALL_CLOCK_LIMIT_S,
                "seeds": seeds,
            })

    if config in ("all", "batch_only"):
        for method, btc, cr in itertools.product(METHODS, batch_task_counts, comm_ranges):
            configs.append({
                "config_name": f"{method}_batch_tc{btc}_cr{cr:.1f}",
                "allocation_method": method,
                "experiment_type": "batch",
                "task_arrival_rate": 0.0,
                "comm_range": cr,
                "initial_tasks": btc,
                "rerun_interval": 999999,
                "max_timesteps": BATCH_MAX_TIMESTEPS,
                "warmup_timesteps": 0,
                "stuck_threshold": STUCK_THRESHOLD,
                "queue_max_depth": QUEUE_MAX_DEPTH,
                "allocation_timeout_s": ALLOCATION_TIMEOUT_S,
                "wall_clock_limit_s": WALL_CLOCK_LIMIT_S,
                "seeds": seeds,
            })

    return configs


# ─────────────────────────────────────────────────────────────────
#  CSV fields written to summary.csv
# ─────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    # Identity
    "run_id", "config_name", "allocation_method", "experiment_type",
    "seed", "num_agents", "task_arrival_rate", "initial_tasks", "comm_range", "rerun_interval",
    # Validity
    "total_steps", "hit_timestep_ceiling", "hit_wall_clock_ceiling",
    # Throughput (steady-state)
    "throughput", "throughput_per_agent", "avg_task_wait_time", "max_task_wait_time",
    "steady_state_tasks_completed", "total_tasks_injected", "tasks_dropped_by_queue_cap", "avg_queue_depth",
    # Batch
    "makespan", "all_tasks_completed", "num_tasks_completed", "num_tasks_total",
    # Computation
    "avg_allocation_time_ms", "avg_allocation_time_per_agent_ms",
    "num_allocation_calls", "max_allocation_time_ms", "std_allocation_time_ms",
    # Communication
    "avg_consensus_rounds_per_call", "total_consensus_rounds",
    # Utilization
    "avg_idle_ratio", "task_balance_std",
    # Distance / Energy
    "distance_per_task", "total_distance_all_agents",
    "total_energy_consumed", "charging_time_fraction", "num_charging_events",
    # Robustness
    "num_deadlocks",
    # Wall-clock
    "wall_time_seconds",
]


# ─────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────

def _run_task(task: Dict):
    """Execute one (cfg, seed) experiment. Module-level for ProcessPoolExecutor pickling."""
    if task["experiment_type"] == "steady_state":
        metrics = run_single_steady_state_experiment(
            config_path=task["config_path"],
            config_name=task["config_name"],
            task_arrival_rate=task["task_arrival_rate"],
            queue_max_depth=task["queue_max_depth"],
            warmup_timesteps=task["warmup_timesteps"],
            comm_range=task["comm_range"],
            rerun_interval=task["rerun_interval"],
            stuck_threshold=task["stuck_threshold"],
            seed=task["seed"],
            max_timesteps=task["max_timesteps"],
            allocation_method=task["allocation_method"],
            initial_tasks=task["initial_tasks"],
            allocation_timeout_s=task["allocation_timeout_s"],
            wall_clock_limit_s=task["wall_clock_limit_s"],
            max_plan_time=task["max_plan_time"],
        )
    else:
        metrics = run_single_batch_experiment(
            config_path=task["config_path"],
            config_name=task["config_name"],
            initial_tasks=task["initial_tasks"],
            queue_max_depth=task["queue_max_depth"],
            comm_range=task["comm_range"],
            rerun_interval=task["rerun_interval"],
            stuck_threshold=task["stuck_threshold"],
            seed=task["seed"],
            max_timesteps=task["max_timesteps"],
            allocation_method=task["allocation_method"],
            allocation_timeout_s=task["allocation_timeout_s"],
            wall_clock_limit_s=task["wall_clock_limit_s"],
            max_plan_time=task["max_plan_time"],
        )
    return metrics, task["label"]


def _save_run_metrics(metrics: RunMetrics, output_dir: str) -> None:
    """Save full metrics dataclass as JSON in a per-run subdirectory."""
    run_dir = os.path.join(output_dir, metrics.run_id)
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "metrics.json"), "w") as f:
        json.dump(asdict(metrics), f, indent=2, default=str)


def _save_summary_csv(all_metrics: List[RunMetrics], output_dir: str) -> None:
    """Write focused summary CSV."""
    summary_path = os.path.join(output_dir, "summary.csv")
    with open(summary_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for m in all_metrics:
            writer.writerow({k: getattr(m, k) for k in CSV_FIELDS})
    print(f"\nSummary CSV: {summary_path}  ({len(all_metrics)} runs)")


def _print_result(metrics: RunMetrics, run_num: int, total_runs: int) -> None:
    if metrics.experiment_type == "steady_state":
        print(
            f"  [DONE {run_num}/{total_runs}] {metrics.allocation_method} "
            f"ar={metrics.task_arrival_rate:.4f} cr={metrics.comm_range:.1f} "
            f"→ throughput={metrics.throughput:.4f} wait={metrics.avg_task_wait_time:.1f}ts"
        )
    else:
        print(
            f"  [DONE {run_num}/{total_runs}] {metrics.allocation_method} "
            f"tc={metrics.initial_tasks} cr={metrics.comm_range:.1f} "
            f"→ makespan={metrics.makespan} completed={metrics.all_tasks_completed}"
        )


def main():
    parser = argparse.ArgumentParser(description="Thesis Experiment Runner")

    parser.add_argument(
        "--config",
        choices=[
            "all", 
            "ss_only", 
            "batch_only",
            "cbba_only",
            "sga_only",
            "dmchba_only",
            "baseline_only"
        ],
        default="all",
        help=(
            "Which experiment configuration to run. Options: "
            "all (default)"
            "'ss_only' = Steady State configs (task_arrival_rate >0). "
            "'batch_only' = Batch processing configs. (initial_tasks >0, task_arrival_rate=0). "
            "'lcba_static_only' = LCBA static -- concensus run only on trigger, no periodic consensus. "
            "'lcba_dynamic_only' = LCBA dynamic -- periodic consensus every N iterations, regardless of triggers. "
            "'cbba_only' = CBBA-specific baseline configs. "
            "'sga_only' = SGA-specific baseline configs. "
            "'dmchba_only' = DMCHBA-specific baseline configs. "
            "'baseline_only' = Baseline comparison configs. -- includes CBBA, SGA, and DMCHBA"
        )
    )

    parser.add_argument(
        "--mode",
        choices=["quick", "full"],
        default="full",
    )

    parser.add_argument(
        "--output",
        default=None,
        help="Override default output directory (results/experiments/<timestamp>)",
    )

    parser.add_argument(
        "--map",
        default="gridworld_warehouse_small",
        help="Which map to run experiments on (default: gridworld_warehouse_small)",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Number of parallel workers (default: 0 = use all CPU cores)",
    )

    args = parser.parse_args()

    map_name = args.map.replace(".yaml", "")

    map_path = os.path.join(PROJECT_ROOT, "config", f"{map_name}.yaml")
    if not os.path.exists(map_path):
        print(f"ERROR: map file not found for map '{map_name}': {map_path}")
        sys.exit(1)

    with open(map_path) as f:
        cfg = yaml.safe_load(f)
    _params = cfg["create_gridworld_node"]["ros__parameters"]
    _map_num_agents = len(_params["agent_positions"]) // 4
    _map_num_induct  = len(_params["induct_stations"]) // 4
    _grid_w = _params.get("grid_width", 30)
    _grid_h = _params.get("grid_height", 30)
    _map_plan_time = max(200, _grid_w + _grid_h)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output if args.output else os.path.join(PROJECT_ROOT, "results", "experiments", map_name, timestamp)
    os.makedirs(output_dir, exist_ok=True)

    configs = get_experiment_configs(
        args.mode,
        args.config,
        num_agents=_map_num_agents,
        num_induct=_map_num_induct,
        grid_w=_grid_w,
        grid_h=_grid_h,
        map_path=map_path,
        )

    num_workers = args.workers if args.workers > 0 else os.cpu_count()
    total_runs = sum(len(cfg["seeds"]) for cfg in configs)

    print(f"\n{'='*70}")
    print(f"Thesis Experiments | map={map_name} | agents={_map_num_agents} | {total_runs} total runs")
    print(f"Comm ranges:       {sorted(set(c['comm_range'] for c in configs))}")
    print(f"SS arrival rates:  {sorted(set(c['task_arrival_rate'] for c in configs if c['experiment_type'] == 'steady_state'))}")
    print(f"Batch task counts: {sorted(set(c['initial_tasks'] for c in configs if c['experiment_type'] == 'batch'))}")
    print(f"Output dir:        {output_dir}")

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
                "experiment_type": cfg["experiment_type"],
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
                    f"{cfg['config_name']} seed={seed}"
                )
            })

    all_metrics: List[RunMetrics] = []

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