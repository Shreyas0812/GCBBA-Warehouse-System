from dataclasses import dataclass


@dataclass
class SensitivityMetrics:
    # ── Identity ──
    run_id: str = ""
    config_name: str = ""
    seed: int = 0
    rerun_interval: int = 0           # *** KEY variable being swept ***
    task_arrival_rate: float = 0.0    # load level — determines whether ri matters at all (ri only matters under load)
    comm_range: float = 0.0           # fixed at one value; here only for traceability

    # ── Run validity ── (discard rows where these are True)
    total_steps: int = 0
    hit_timestep_ceiling: bool = False      # run didn't finish in time → increase MAX_TIMESTEPS
    hit_wall_clock_ceiling: bool = False    # run hit wall-clock cap → increase WALL_CLOCK_LIMIT_S

    # ── PRIMARY: select ri on these ──
    throughput: float = 0.0               # *** tasks/ts post-warmup — main decision metric ***
    avg_task_wait_time: float = 0.0       # *** how long tasks sit in queue before being picked up ***

    # ── SECONDARY: understand load context ──
    avg_queue_depth: float = 0.0          # mean pending tasks per station — high = system is overloaded
    queue_saturation_fraction: float = 0.0  # fraction of timesteps where any station hit the queue cap
    tasks_dropped_by_queue_cap: int = 0   # tasks lost to overflow — nonzero means arrival >> capacity
    steady_state_tasks_completed: int = 0  # raw count (numerator of throughput)
    total_tasks_injected: int = 0         # total tasks that arrived (denominator context)

    # ── DID ri EVEN FIRE? ── (if 0 for all finite ri values → ri is useless on this map)
    num_gcbba_runs: int = 0                        # total allocation calls (all triggers combined)
    num_gcbba_runs_interval_triggered: int = 0     # *** calls caused specifically by rerun_interval ***

    # ── COST of ri ── (higher ri → more overhead; is the throughput gain worth it?)
    avg_gcbba_time_ms: float = 0.0    # per-call allocation cost
    total_gcbba_time_ms: float = 0.0  # total time spent in GCBBA across the run

    # ── INTERPRETATION ── (helps explain throughput differences)
    avg_idle_ratio: float = 0.0    # fraction of timesteps agents are idle — high idle + low throughput → allocation problem
    task_balance_std: float = 0.0  # std of tasks completed per agent — high = uneven distribution

    # ── Wall clock ──
    wall_time_seconds: float = 0.0  # real time to run this experiment (useful for estimating sweep cost)

    @classmethod
    def from_run_metrics(cls, m) -> "SensitivityMetrics":
        return cls(
            run_id=m.run_id,
            config_name=m.config_name,
            seed=m.seed,
            rerun_interval=m.rerun_interval,
            task_arrival_rate=m.task_arrival_rate,
            comm_range=m.comm_range,
            total_steps=m.total_steps,
            hit_timestep_ceiling=m.hit_timestep_ceiling,
            hit_wall_clock_ceiling=m.hit_wall_clock_ceiling,
            throughput=m.throughput,
            avg_task_wait_time=m.avg_task_wait_time,
            avg_queue_depth=m.avg_queue_depth,
            queue_saturation_fraction=m.queue_saturation_fraction,
            tasks_dropped_by_queue_cap=m.tasks_dropped_by_queue_cap,
            steady_state_tasks_completed=m.steady_state_tasks_completed,
            total_tasks_injected=m.total_tasks_injected,
            num_gcbba_runs=m.num_gcbba_runs,
            num_gcbba_runs_interval_triggered=m.num_gcbba_runs_interval_triggered,
            avg_gcbba_time_ms=m.avg_gcbba_time_ms,
            total_gcbba_time_ms=m.total_gcbba_time_ms,
            avg_idle_ratio=m.avg_idle_ratio,
            task_balance_std=m.task_balance_std,
            wall_time_seconds=m.wall_time_seconds,
        )
