"""
run_single_experiment.py
========================
Single-run runners for the main thesis comparison experiments (GCBBA vs CBBA vs SGA).
Collects all RunMetrics fields.

See run_single_ri_sensitivity_experiment.py for the rerun_interval sensitivity runner.
"""

import os
import sys
import time

import numpy as np

from typing import Optional, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from integration.orchestrator import IntegrationOrchestrator
from Metrics import RunMetrics

class MetricsOrchestrator(IntegrationOrchestrator):
    """
    Extended instrumentation that collects all RunMetrics fields.
    Tracks allocation timing, consensus rounds, charging, deadlocks,
    and per-agent distance/energy.
    """

    def __init__(self, *args, **kwargs):
        self._wall_time_limit_s: Optional[float] = kwargs.pop("wall_clock_limit_s", None)
        kwargs.pop("allocation_timeout_s", None)
        super().__init__(*args, **kwargs)

        self._hit_wall_clock_ceiling: bool = False

        # Allocation timing
        self._allocation_times_ms: List[float] = []
        self._allocation_call_timesteps: List[int] = []
        self._tasks_per_allocation_call: List[int] = []

        # Charging
        self._total_charging_timesteps: int = 0
        self._num_charging_events: int = 0
        self._prev_navigating: List[bool] = []   # populated on first step

        # Deadlocks (stuck-state entry events)
        self._num_deadlocks: int = 0
        self._prev_stuck: List[bool] = []        # populated on first step

        # Time series
        self._tasks_completed_over_time: List[int] = []
    
    def run_allocation(self) -> None:
        pending = len(self._pending_task_ids)
        t0 = time.perf_counter()
        IntegrationOrchestrator.run_allocation(self)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self._allocation_times_ms.append(elapsed_ms)
        self._allocation_call_timesteps.append(self.current_timestep)
        self._tasks_per_allocation_call.append(pending)

    def run_simulation(self, timesteps: int = 100) -> None:
        from tqdm import tqdm
        wall_start = time.perf_counter()
        pbar = tqdm(range(timesteps), desc=f"Simulation ({self.allocation_method.upper()})", leave=True)
        for _ in pbar:
            if self._wall_time_limit_s is not None:
                if time.perf_counter() - wall_start > self._wall_time_limit_s:
                    self._hit_wall_clock_ceiling = True
                    tqdm.write(
                        f"[t={self.current_timestep}] WALL-CLOCK LIMIT "
                        f"({self._wall_time_limit_s / 60:.0f} min) exceeded — stopping early."
                    )
                    break
            self.step()
            q = float(np.mean(list(self._induct_queue_depth.values()))) if self._induct_queue_depth else 0
            pbar.set_postfix(done=len(self.completed_task_ids), t=self.current_timestep, q=f"{q:.2f}", refresh=False)

    def step(self, *args, **kwargs):
        # Initialise per-agent state tracking on first step
        if not self._prev_navigating:
            self._prev_navigating = [s.is_navigating_to_charger for s in self.agent_states]
            self._prev_stuck = [s.is_stuck for s in self.agent_states]

        result = super().step(*args, **kwargs)

        for i, s in enumerate(self.agent_states):
            # New charging event: agent just started navigating to charger
            if s.is_navigating_to_charger and not self._prev_navigating[i]:
                self._num_charging_events += 1
            self._prev_navigating[i] = s.is_navigating_to_charger

            # Charging timesteps
            if s.is_charging:
                self._total_charging_timesteps += 1

            # Deadlock: agent just became stuck
            currently_stuck = s.detect_stuck(self.stuck_threshold)
            if currently_stuck and not self._prev_stuck[i]:
                self._num_deadlocks += 1
            self._prev_stuck[i] = currently_stuck

        self._tasks_completed_over_time.append(len(self.completed_task_ids))
        return result
    
    def collect_steady_state_metrics(self, warmup_timesteps: int, **kwargs) -> RunMetrics:
        """Collect metrics for a steady-state run (throughput, wait time, queue depth)."""
        m = RunMetrics()
        m.num_tasks_completed = len(self.completed_task_ids)
        # self._collect_common_metrics(m, **kwargs)

        # ── Throughput ────────────────────────────────────────────
        m.total_tasks_injected = self._next_task_id
        m.tasks_dropped_by_queue_cap = self._tasks_dropped_by_cap
        if self._queue_depth_snapshots:
            m.avg_queue_depth = round(float(np.mean(self._queue_depth_snapshots)), 3)

        seen: set = set()
        ss_tasks = []
        for s in self.agent_states:
            for t in s.completed_tasks:
                if t.task_id not in seen and t.start_time is not None and t.start_time >= warmup_timesteps:
                    seen.add(t.task_id)
                    ss_tasks.append(t)
        ss_steps = max(1, self.current_timestep - warmup_timesteps)
        m.steady_state_tasks_completed = len(ss_tasks)
        m.throughput = round(len(ss_tasks) / ss_steps, 4)
        m.throughput_per_agent = round(m.throughput / kwargs["num_agents"], 6) if kwargs.get("num_agents") else 0.0

        wait_times = []
        for t in ss_tasks:
            inj = self._task_injection_time.get(t.task_id)
            if inj is not None and t.start_time is not None:
                wait_times.append(t.start_time - inj)
        if wait_times:
            m.avg_task_wait_time = round(float(np.mean(wait_times)), 2)
            m.max_task_wait_time = round(float(max(wait_times)), 2)

        return m