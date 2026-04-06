"""
Experiment Runner: 

Usage:
  python run_experiments.py --mode quick    # ~8 runs, verify pipeline
  python run_experiments.py --mode medium   # ~216 runs, initial results
  python run_experiments.py --mode full     # ~720 runs, thesis data
"""

import argparse
import os
import sys
from typing import List, Dict
import yaml as yaml
from datetime import datetime
import itertools

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def get_experiment_configs(
    mode: str = 'full',
    config:str = 'all',
    num_agents: int = 6,
    num_induct: int = 8,
    grid_w: int = 30,
    grid_h: int = 30,
) -> List[Dict]:
    """
    Builds list of experiment configurations to run based on the selected mode and map parameters. 
     - mode: 'quick', 'medium', or 'full' to select which subset of experiments to run.
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
    # Average task service time: half the Manhattan perimeter of the grid.
    avg_service_time = (grid_w + grid_h) / 2
    capacity = num_agents / (avg_service_time * num_induct)
    diagonal = (grid_w ** 2 + grid_h ** 2) ** 0.5

    if mode == "quick":
        seeds = [42]
        # Knee (1×) and a heavy-load point (2×) only
        capacity_fracs = [1.0, 2.0] 
        # One sparse range (35% diagonal) and one full-connectivity range
        range_fracs = [0.35, 1.2] 
        rerun_intervals = [50]
        batch_task_counts = [80]

    elif mode == "medium":
        seeds = [42, 123, 456]
        capacity_fracs = [0.5, 1.0, 1.5, 2.0]
        # Light → knee → overload → heavy
        range_fracs = [0.1, 0.2, 0.35, 1.2]
        rerun_intervals = [25, 50, 100]
        batch_task_counts = [40, 80, 160]

    else:  # full
        seeds = [42, 123, 456, 789, 1024]
        # 10 points from 25% to 300% of capacity
        capacity_fracs = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0]
        # 6 points spanning near-disconnected to full-connectivity
        range_fracs = [0.05, 0.1, 0.2, 0.35, 0.6, 1.2]
        rerun_intervals = [10, 25, 50, 100, 200]
        batch_task_counts = [20, 40, 80, 160]
    
    arrival_rates = sorted(set(
        max(0.001, round(f * capacity, 4)) for f in capacity_fracs
    ))
    comm_ranges = sorted(set(
        max(3, round(f * diagonal)) for f in range_fracs
    ))

    STUCK_THRESHOLD = 15
    MAX_TIMESTEPS = 1500
    WARMUP_TIMESTEPS = 300
    QUEUE_MAX_DEPTH = 10
    BATCH_MAX_TIMESTEPS = 3000
    SS_INITIAL_TASKS = 2 * num_agents

    ALLOCATION_TIMEOUT_S = 10.0
    WALL_CLOCK_LIMIT_S = 600.0

    for ar, cr in itertools.product(arrival_rates, comm_ranges):
        if config in ("all", "ss_only"):
            configs.append({
                "experiment_type": "steady_state",
                "arrival_rate": ar,
                "comm_range": cr,
                "initial_tasks": SS_INITIAL_TASKS,
                "rerun_interval": 999999,  # no periodic reruns in steady state
                "max_timesteps": MAX_TIMESTEPS,
                "warmup_timesteps": WARMUP_TIMESTEPS,
                "stuck_threshold": STUCK_THRESHOLD,
                "queue_max_depth": QUEUE_MAX_DEPTH,
                "allocation_timeout_s": ALLOCATION_TIMEOUT_S,
                "wall_clock_limit_s": WALL_CLOCK_LIMIT_S,
            })
        if config in ("all", "batch_only"):
            for btc in batch_task_counts:
                configs.append({
                    "experiment_type": "batch",
                    "arrival_rate": 0.0,  # no arrivals in batch mode
                    "comm_range": cr,
                    "initial_tasks": btc,
                    "rerun_interval": 999999,  # no periodic reruns in batch mode
                    "max_timesteps": BATCH_MAX_TIMESTEPS,
                    "warmup_timesteps": 0,
                    "stuck_threshold": STUCK_THRESHOLD,
                    "queue_max_depth": QUEUE_MAX_DEPTH,
                    "allocation_timeout_s": ALLOCATION_TIMEOUT_S,
                    "wall_clock_limit_s": WALL_CLOCK_LIMIT_S,
                })
        if config in ("all", "sensitivity_only"):
            for ri in rerun_intervals:
                configs.append({
                    "experiment_type": "dynamic",
                    "arrival_rate": ar,
                    "comm_range": cr,
                    "initial_tasks": SS_INITIAL_TASKS,
                    "rerun_interval": ri,  # periodic reruns every N timesteps
                    "max_timesteps": MAX_TIMESTEPS,
                    "warmup_timesteps": WARMUP_TIMESTEPS,
                    "stuck_threshold": STUCK_THRESHOLD,
                    "queue_max_depth": QUEUE_MAX_DEPTH,
                    "allocation_timeout_s": ALLOCATION_TIMEOUT_S,
                    "wall_clock_limit_s": WALL_CLOCK_LIMIT_S,
                })

    return configs


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
            "baseline_only",
            "sensitivity_only"
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
            "'sensitivity_only' = LCBA Sensitivity analysis configs -- runs dynamic LCBA for seperate rerun intervals to analyze convergence and performance trends."
        )
    )

    parser.add_argument(
        "--mode",
        choices=["quick", "medium", "full"],
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
    ),

    args = parser.parse_args()

    map_name = args.map.replace(".yaml", "")

    config_path = os.path.join(PROJECT_ROOT, "config", f"{map_name}.yaml")
    if not os.path.exists(config_path):
        print(f"ERROR: config file not found for map '{map_name}': {config_path}")
        sys.exit(1)

    with open(config_path) as f:
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
        grid_w =_grid_w,
        grid_h=_grid_h
        )


if __name__ == "__main__":
    main()