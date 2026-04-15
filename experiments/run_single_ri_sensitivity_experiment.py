"""
run_single_experiment.py
========================
Stripped-down runner for the rerun_interval sensitivity experiment.
Tracks only fields required by SensitivityMetrics.
"""

import os
import sys
import time
from typing import List, Optional

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from integration.orchestrator import IntegrationOrchestrator
from SensitivityMetrics import SensitivityMetrics


# ─────────────────────────────────────────────────────────────────
#  SensitivityOrchestrator
# ─────────────────────────────────────────────────────────────────

class SensitivityOrchestrator(IntegrationOrchestrator):
    def __init__(self, *args, **kwargs):
        self._wall_time_limit_s: Optional[float] = kwargs.pop("wall_clock_limit_s", None)
        kwargs.pop("allocation_timeout_s", None)  # not used for gcbba, discard
        super().__init__(*args, **kwargs)

        self._hit_wall_clock_ceiling: bool = False

        # GCBBA timing
        self._gcbba_run_count: int = 0
        self._gcbba_times_ms: List[float] = []

        # Trigger classification: batch completion vs interval timer
        self._gcbba_batch_triggers: int = 0
        self._gcbba_interval_triggers: int = 0

    def run_allocation(self) -> None:
        t0 = time.perf_counter()
        IntegrationOrchestrator.run_allocation(self)
        self._gcbba_times_ms.append((time.perf_counter() - t0) * 1000.0)
        self._gcbba_run_count += 1

    def run_simulation(self, timesteps: int = 100) -> None:
        from tqdm import tqdm
        wall_start = time.perf_counter()
        pbar = tqdm(range(timesteps), desc="Simulation (GCBBA)", leave=True)
        for _ in pbar:
            if self._wall_time_limit_s is not None:
                elapsed = time.perf_counter() - wall_start
                if elapsed > self._wall_time_limit_s:
                    self._hit_wall_clock_ceiling = True
                    tqdm.write(
                        f"[t={self.current_timestep}] WALL-CLOCK LIMIT "
                        f"({self._wall_time_limit_s / 60:.0f} min) exceeded — stopping early."
                    )
                    break
            self.step()
            q = (
                float(np.mean(list(self._induct_queue_depth.values())))
                if self._induct_queue_depth else 0
            )
            pbar.set_postfix(done=len(self.completed_task_ids), t=self.current_timestep, q=f"{q:.2f}", refresh=False)

    def step(self, *args, **kwargs):
        completed_before = len(self.completed_task_ids)
        completed_at_last_gcbba_before = self._completed_at_last_gcbba

        events = super().step(*args, **kwargs)

        if events.gcbba_rerun:
            batch_threshold = max(2, self.num_agents // 3)
            completed_since_last = completed_before - completed_at_last_gcbba_before
            if completed_since_last >= batch_threshold:
                self._gcbba_batch_triggers += 1
            else:
                self._gcbba_interval_triggers += 1

        return events

    def collect_sensitivity_metrics(
        self,
        config_name: str,
        seed: int,
        task_arrival_rate: float,
        warmup_timesteps: int,
        comm_range: float,
        rerun_interval: int,
        wall_time: float,
        max_timesteps: int,
    ) -> SensitivityMetrics:
        m = SensitivityMetrics()

        # Identity
        m.config_name = config_name
        m.seed = seed
        m.task_arrival_rate = task_arrival_rate
        m.comm_range = comm_range
        m.rerun_interval = rerun_interval
        m.run_id = f"{config_name}_ar{task_arrival_rate}_cr{int(comm_range)}_s{seed}"

        # Outcome
        m.total_steps = self.current_timestep
        m.hit_timestep_ceiling = (
            not (self.completed_task_ids >= self.all_task_ids)
            and self.current_timestep >= max_timesteps - 1
        )
        m.hit_wall_clock_ceiling = self._hit_wall_clock_ceiling
        m.wall_time_seconds = round(wall_time, 3)

        # GCBBA allocation
        m.num_gcbba_runs = self._gcbba_run_count
        m.num_gcbba_runs_interval_triggered = self._gcbba_interval_triggers
        m.total_gcbba_time_ms = round(sum(self._gcbba_times_ms), 2)
        m.avg_gcbba_time_ms = round(float(np.mean(self._gcbba_times_ms)), 2) if self._gcbba_times_ms else 0.0

        # Steady-state throughput
        m.total_tasks_injected = self._next_task_id
        m.tasks_dropped_by_queue_cap = self._tasks_dropped_by_cap

        seen_ss_ids: set = set()
        ss_tasks = []
        for agent_state in self.agent_states:
            for task in agent_state.completed_tasks:
                if (
                    task.start_time is not None
                    and task.start_time >= warmup_timesteps
                    and task.task_id not in seen_ss_ids
                ):
                    seen_ss_ids.add(task.task_id)
                    ss_tasks.append(task)
        ss_steps = max(1, self.current_timestep - warmup_timesteps)
        m.steady_state_tasks_completed = len(ss_tasks)
        m.throughput = round(len(ss_tasks) / ss_steps, 4)

        wait_times = []
        for task in ss_tasks:
            inj_t = self._task_injection_time.get(task.task_id)
            if inj_t is not None and task.start_time is not None:
                wait_times.append(task.start_time - inj_t)
        if wait_times:
            m.avg_task_wait_time = round(float(np.mean(wait_times)), 2)

        if self._queue_depth_snapshots:
            m.avg_queue_depth = round(float(np.mean(self._queue_depth_snapshots)), 3)
            sat_count = sum(
                1 for s in self._queue_depth_snapshots if s >= self.induct_queue_capacity
            )
            m.queue_saturation_fraction = round(sat_count / len(self._queue_depth_snapshots), 4)

        # Agent utilization
        idle_ratios, tasks_per_agent = [], []
        for agent_state in self.agent_states:
            hist = agent_state.position_history
            total = max(len(hist), 1)
            idle = sum(1 for k in range(1, len(hist)) if hist[k - 1][:3] == hist[k][:3])
            idle_ratios.append(idle / total)
            tasks_per_agent.append(len(agent_state.completed_tasks))
        m.avg_idle_ratio = round(float(np.mean(idle_ratios)), 4) if idle_ratios else 0.0
        m.task_balance_std = round(float(np.std(tasks_per_agent)), 3) if tasks_per_agent else 0.0

        return m


# ─────────────────────────────────────────────────────────────────
#  Single experiment runner
# ─────────────────────────────────────────────────────────────────

def run_single_sensitivity_experiment(
    config_path: str,
    config_name: str,
    task_arrival_rate: float,
    queue_max_depth: int,
    warmup_timesteps: int,
    comm_range: float,
    rerun_interval: int,
    stuck_threshold: int,
    seed: int,
    max_timesteps: int,
    allocation_method: str = "gcbba",
    initial_tasks: int = 0,
    allocation_timeout_s: Optional[float] = None,
    wall_clock_limit_s: Optional[float] = None,
    max_plan_time: int = 200,
) -> SensitivityMetrics:
    np.random.seed(seed)

    orch = SensitivityOrchestrator(
        config_path=config_path,
        task_arrival_rate=task_arrival_rate,
        induct_queue_capacity=queue_max_depth,
        warmup_timesteps=warmup_timesteps,
        initial_tasks=initial_tasks,
        comm_range=comm_range,
        rerun_interval=rerun_interval,
        stuck_threshold=stuck_threshold,
        max_plan_time=max_plan_time,
        allocation_method=allocation_method,
        allocation_timeout_s=allocation_timeout_s,
        wall_clock_limit_s=wall_clock_limit_s,
    )

    t0 = time.perf_counter()
    orch.run_simulation(timesteps=max_timesteps)
    wall_time = time.perf_counter() - t0

    return orch.collect_sensitivity_metrics(
        config_name, seed, task_arrival_rate,
        warmup_timesteps, comm_range, rerun_interval,
        wall_time, max_timesteps,
    )
