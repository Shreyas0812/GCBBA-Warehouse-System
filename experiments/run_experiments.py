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
import yaml as yaml
from datetime import datetime


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main():
    parser = argparse.ArgumentParser(description="Thesis Experiment Runner")

    parser.add_argument(
        "--config",
        choices=[
            "all", 
            "ss_only", 
            "batch_only",
            "static_only",
            "dynamic_only",
            "cbba_only",
            "sga_only",
            "dmchba_only",
            "baseline_only"
            "sensitivity_only"
        ],
        default="all",
        help=(
            "Which experiment configuration to run. Options: "
            "all (default)"
            "'ss_only' = Steady State configs (task_arrival_rate >0). "
            "'batch_only' = Batch processing configs. (initial_tasks >0, task_arrival_rate=0). "
            "'static_only' = LCBA static -- concensus run only on trigger, no periodic consensus. "
            "'dynamic_only' = LCBA dynamic -- periodic consensus every N iterations, regardless of triggers. "
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
    _params = cfg["create_gridworld_code"]["ros__parameters"]
    _map_num_agents = len(_params["agent_positions"]) // 4
    _map_num_induct  = len(_params["induct_stations"]) // 4
    _grid_w = _params.get("grid_width", 30)
    _grid_h = _params.get("grid_height", 30)
    _map_plan_time = max(200, _grid_w + _grid_h)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output if args.output else os.path.join(PROJECT_ROOT, "results", "experiments", map_name, timestamp)
    os.makedirs(output_dir, exist_ok=True)

    


if __name__ == "__main__":
    main()