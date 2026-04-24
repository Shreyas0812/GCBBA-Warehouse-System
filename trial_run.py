import sys, os, random
sys.path.insert(0, '.'); sys.path.insert(0, 'experiments')
import numpy as np
np.random.seed(42); random.seed(42)

from experiments.run_single_experiment import MetricsOrchestrator

OUT = 'results/trial_multi_planner_rhcr_task'
os.makedirs(OUT, exist_ok=True)

orch = MetricsOrchestrator(
    config_path='config/gridworld_warehouse_small.yaml',
    task_arrival_rate=0.0,
    induct_queue_capacity=10,
    warmup_timesteps=0,
    initial_tasks=76,
    comm_range=11,
    rerun_interval=95,
    stuck_threshold=15,
    max_plan_time=200,
    allocation_method='gcbba',
    allocation_timeout_s=10.0,
    wall_clock_limit_s=2400.0,
    path_planner='ca_star',
    charger_planner='ca_star',
    idle_planner='ca_star',
    task_planner='rhcr',
)

print('Running 3000 timesteps...')
orch.run_simulation(timesteps=3000)

traj_path = os.path.join(OUT, 'trajectories.csv')
orch.save_trajectories(traj_path)

metrics = orch.collect_batch_metrics(
    config_name='trial_multi_planner',
    allocation_method='gcbba',
    path_planner='ca_star+rhcr_task',
    experiment_type='batch',
    seed=42,
    num_agents=len(orch.agent_states),
    task_arrival_rate=0.0,
    initial_tasks=76,
    comm_range=11,
    rerun_interval=95,
    stuck_threshold=15,
    queue_max_depth=10,
    max_timesteps=3000,
    wall_time=0,
)
print(f'\nTasks completed : {metrics.num_tasks_completed}')
print(f'All completed   : {metrics.all_tasks_completed}')
print(f'Makespan        : {metrics.makespan}')
print(f'Collisions      : {metrics.collisions}')
print(f'Deadlocks       : {metrics.num_deadlocks}')

import csv
from collections import Counter

positions = {}
with open(traj_path) as f:
    for row in csv.DictReader(f):
        aid = int(row['agent_id'])
        pos = (int(row['x']), int(row['y']))
        positions.setdefault(aid, []).append(pos)

print('\nPer-agent idle analysis (most common cell and % of time there):')
for aid in sorted(positions):
    hist = Counter(positions[aid])
    top_pos, top_cnt = hist.most_common(1)[0]
    total = len(positions[aid])
    seq = positions[aid]
    moves = sum(1 for i in range(1, total) if seq[i] != seq[i-1])
    print(f'  Agent {aid}: top cell {top_pos} = {top_cnt}/{total} ({100*top_cnt/total:.1f}%)  moves={moves}')
