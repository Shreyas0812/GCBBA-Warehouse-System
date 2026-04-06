import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
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
# from experiments.run_single_experiment import run_single_experiment

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
    range_fracs = [0.35] # 35% (knee) -- Does not affect Rerun Interval sensitivity
    rerun_intervals = [10, 25, 50, 100, 200, 999999]  # 999999 = static (no reruns)

    arrival_rates = sorted(set(max(0.001, round(f * capacity, 4)) for f in capacity_fracs))
    comm_ranges   = sorted(set(max(3, round(f * diagonal))        for f in range_fracs))

    STUCK_THRESHOLD = 15
    MAX_TIMESTEPS = 1500
    WARMUP_TIMESTEPS = 300
    QUEUE_MAX_DEPTH = 10
    SS_INITIAL_TASKS = 2 * num_agents

    ALLOCATION_TIMEOUT_S = 10.0
    WALL_CLOCK_LIMIT_S = 600.0

    for ar, cr in itertools.product(arrival_rates, comm_ranges):
        
        for ri in rerun_intervals:
            configs.append({
                "config_name": f"lcba_dynamic_ar{ar:.4f}_cr{cr:.1f}_ri{ri}",
                "allocation_method": "gcbba",
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
#  Parallel worker (module-level so ProcessPoolExecutor can pickle it)
# ─────────────────────────────────────────────────────────────────

def _run_task(task: Dict):
    """
    Execute one (cfg, seed) experiment and save its per-run results.
    Returns (metrics, label) so the main process can aggregate and print progress.
    Must be a module-level function to be picklable by ProcessPoolExecutor.
    """
    metrics, orch = run_single_experiment(
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
        initial_tasks=task["initial_tasks"],
        allocation_timeout_s=task["allocation_timeout_s"],
        wall_clock_limit_s=task["wall_clock_limit_s"],
        max_plan_time=task["max_plan_time"],
    )
    # save_run_results(metrics, orch, task["output_dir"])
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
        PROJECT_ROOT, "results", "experiments", map_name, "sensitivity", timestamp
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
    
    # print(f"\n{'='*70}")
    # print(f"LCBA Experiments | map={map_name} | agents={_map_num_agents} | {total_runs} total runs | workers={num_workers}")
    # print(f"Arrival rates:   {sorted(set(c['task_arrival_rate'] for c in configs))}")
    # print(f"Comm ranges:     {sorted(set(c['comm_range'] for c in configs))}")
    # print(
    #     f"Rerun intervals: "
    #     f"{sorted(set(c['rerun_interval'] for c in configs if c['rerun_interval'] < 999999))}"
    # )
    # print(f"Output:          {output_dir}")
    # print(f"{'='*70}\n")

    # # Save experiment metadata + machine info
    # machine_info = collect_machine_info()
    # with open(os.path.join(output_dir, "experiment_config.json"), "w") as f:
    #     json.dump(
    #         {
    #             "mode": args.mode,
    #             "config_filter": ,
    #             "map": map_name,
    #             "timestamp": timestamp,
    #             "total_runs": total_runs,
    #             "workers": num_workers,
    #             "machine": machine_info,
    #             "configs": configs,
    #         },
    #         f,
    #         indent=2,
    #     )

    # # Build flattened list of (config, seed) pairs for execution
    # tasks = []
    # for cfg in configs:
    #     for seed in cfg["seeds"]:
    #         tasks.append({
    #             "config_path": config_path,
    #             "config_name": cfg["config_name"],
    #             "task_arrival_rate": cfg["task_arrival_rate"],
    #             "queue_max_depth": cfg["queue_max_depth"],
    #             "warmup_timesteps": cfg["warmup_timesteps"],
    #             "comm_range": cfg["comm_range"],
    #             "rerun_interval": cfg["rerun_interval"] if cfg["rerun_interval"] < 999999 else "ri-static",
    #             "stuck_threshold": cfg["stuck_threshold"],
    #             "seed": seed,
    #             "max_timesteps": cfg["max_timesteps"],
    #             "allocation_method": cfg["allocation_method"],
    #             "initial_tasks": cfg["initial_tasks"],
    #             "allocation_timeout_s": cfg["allocation_timeout_s"],
    #             "wall_clock_limit_s": cfg["wall_clock_limit_s"],
    #             "max_plan_time": _map_plan_time,
    #             "output_dir": output_dir,
    #             "label": (
    #                 f"{cfg['config_name']} "
    #                 f"ar{cfg['task_arrival_rate']:.4f} "
    #                 f"cr{cfg['comm_range']:.1f} "
    #                 f"{cfg['rerun_interval'] if cfg['rerun_interval'] < 999999 else 'ri-static'} "
    #                 f"seed={seed}"
    #             )
    #         })

    # # ────────────────────────────────────────────────────────────────────────────────────
    # # At this point we have a list of tasks to run, each with a config and seed. We can now execute these in parallel using ProcessPoolExecutor.
    # # Each task will run the experiment with the specified config and seed, and save its results

    # all_metrics = []

    # if num_workers == 1:
    #     print("Running experiments sequentially...")
    #     for run_num, task in enumerate(tasks, 1):
    #         print(f"\n[RUN {run_num}/{total_runs}] {task['label']}")
    #         try:
    #             metrics, label = _run_task(task)
    #             all_metrics.append(metrics)
    #             # _print_result(metrics, label, run_num)
    #         except Exception as e:
    #             print(f"ERROR in run {task['label']}: {e}")
    #             traceback.print_exc()
    # else:
    #     completed = 0
    #     with ProcessPoolExecutor(max_workers=num_workers) as executor:
    #         future_to_task = {executor.submit(_run_task, task): task for task in tasks}
    #         for future in as_completed(future_to_task):
    #             task = future_to_task[future]
    #             completed += 1
    #             try:
    #                 metrics, label = future.result()
    #                 all_metrics.append(metrics)
    #                 completed += 1
    #                 print(f"\n[COMPLETED {completed}/{total_runs}] {label}")
    #                 # _print_result(metrics, label, completed)
    #             except Exception as e:
    #                 print(f"ERROR in run {task['label']}: {e}")
    #                 traceback.print_exc()

    # if all_metrics:
    #     pass
    #     # save_summary_csv(all_metrics, output_dir)
    #     # compute_and_save_optimality_ratios(output_dir)

if __name__ == "__main__":
    main()