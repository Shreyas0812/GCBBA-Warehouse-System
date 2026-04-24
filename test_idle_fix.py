import os, sys
PROJECT_ROOT = r"C:\Users\shrey\OneDrive\Documents\Upenn\Thesis\GCBBA_Warehouse_System"
EXPERIMENTS_DIR = os.path.join(PROJECT_ROOT, "experiments")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, EXPERIMENTS_DIR)

from run_single_experiment import run_single_batch_experiment

config_path = os.path.join(PROJECT_ROOT, "config", "gridworld_warehouse_small.yaml")
out_dir = os.path.join(PROJECT_ROOT, "results", "test_idle_fix")

print("[TEST] Running batch experiment with pending_tasks fix...")
print(f"  Config: {config_path}")
print(f"  Output: {out_dir}")
print()

metrics = run_single_batch_experiment(
    config_path=config_path,
    config_name="test_idle_fix",
    initial_tasks=40,
    queue_max_depth=10,
    comm_range=15,
    rerun_interval=999999,
    stuck_threshold=15,
    seed=42,
    max_timesteps=1500,
    allocation_method="gcbba",
    allocation_timeout_s=10.0,
    wall_clock_limit_s=240.0,
    max_plan_time=300,
    path_planner="ca_star",
    output_dir=out_dir,
)

print()
print("=" * 60)
print("[RESULTS]")
print(f"  Tasks completed:  {metrics.num_tasks_completed} / {metrics.num_tasks_total}")
print(f"  All tasks done:   {metrics.all_tasks_completed}")
print(f"  Makespan:         {metrics.makespan}")
print("=" * 60)

if metrics.num_tasks_completed == metrics.num_tasks_total:
    print("✓ SUCCESS: All tasks completed!")
else:
    print(f"✗ FAILURE: Only {metrics.num_tasks_completed}/{metrics.num_tasks_total} tasks completed")
    print(f"  Missing {metrics.num_tasks_total - metrics.num_tasks_completed} tasks")
