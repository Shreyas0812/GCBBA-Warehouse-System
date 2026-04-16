# Shelved Ideas

## Batch Mode: Workload Drain Metrics

**Context:** Steady-state mode tracks `avg_queue_depth` (mean pending tasks per induct station over time). There is no direct equivalent in batch mode since all tasks are injected at t=0 and the queue simply drains.

**Potential additions for batch mode:**

- **Tasks remaining over time** — `len(all_task_ids - completed_task_ids)` snapshot per timestep. Shows how fast the system drains the workload. Analogous to queue depth but in reverse (starts at N, goes to 0).
- **Agent utilization over time** — fraction of agents actively executing (not idle/charging) at each timestep. High utilization = efficient; drops near end = stragglers.

**Why useful:** Would allow time-series plots comparing how different algorithms (GCBBA vs CBBA vs SGA) drain the workload — e.g. does GCBBA drain faster in the first half, does SGA catch up later?

**Why deferred:** `makespan` already captures the end result implicitly. Time-series versions are only needed for within-run trajectory comparisons, not cross-condition tables. Low priority until thesis figures require it.

**Status: Already implemented.**
- `queue_depth_over_time` (per-timestep `_queue_depth_snapshots`) is saved in `metrics.json` for every run.
- `tasks_completed_over_time` (per-timestep cumulative completed count) is also saved in `metrics.json`.
Both are full time-series and available for plotting directly from the JSON output. No further implementation needed.
