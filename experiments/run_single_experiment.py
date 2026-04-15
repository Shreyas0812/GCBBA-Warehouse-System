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