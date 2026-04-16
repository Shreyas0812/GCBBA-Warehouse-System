# Metrics Guide

What each metric in `RunMetrics` identifies, framed around the GCBBA vs CBBA vs SGA comparison.

The metrics that most directly support the thesis claim (GCBBA is better) are `avg_consensus_rounds_per_call` (vs CBBA), `solution_quality_ratio` + `task_balance_std` + `distance_per_task` (vs SGA), and `throughput` under heavy load (vs both).

---

## Throughput (steady-state)

| Metric | What it identifies |
|---|---|
| `throughput` | Overall system capacity — does better allocation actually move more items? |
| `avg_task_wait_time` | Allocation responsiveness — how long do tasks sit unstarted after arriving? |
| `max_task_wait_time` | Worst-case starvation — does any algorithm leave tasks unattended for a long time? |
| `tasks_dropped_by_queue_cap` | Overload behavior — which algorithm degrades most gracefully under heavy load? |
| `avg_queue_depth` | Backpressure — is the system keeping up, or are tasks piling up? |

## Batch Completion

| Metric | What it identifies |
|---|---|
| `makespan` | End-to-end efficiency on a fixed task set |
| `solution_quality_ratio` | How far each algorithm is from optimal (Hungarian) |

## Computation

| Metric | What it identifies |
|---|---|
| `avg_allocation_time_ms` | Raw cost per decision — is GCBBA's overhead acceptable? |
| `avg_allocation_time_per_agent_ms` | Scalability of cost — does it grow with fleet size? |
| `max_allocation_time_ms` | Worst-case latency — could a slow allocation stall the sim? |
| `std_allocation_time_ms` | Consistency — does allocation time vary a lot run-to-run? |
| `num_allocation_timeouts` | Reliability — did any calls fail to finish in time? |
| `avg_tasks_per_allocation_call` | Context for the above — larger problem = slower is expected |

## Communication

| Metric | What it identifies |
|---|---|
| `avg_consensus_rounds_per_call` | **Key differentiator**: GCBBA should need fewer rounds than CBBA because global info eliminates conflicting local views |

## Utilization

| Metric | What it identifies |
|---|---|
| `avg_idle_ratio` | Wasted capacity — are agents sitting idle while tasks wait? |
| `task_balance_std` | Fairness — does one algorithm overload some agents while others coast? |
| `std_idle_ratio` | Unevenness of idleness across agents |

## Path / Distance

| Metric | What it identifies |
|---|---|
| `distance_per_task` | Assignment quality — better allocation = shorter average travel per task |
| `total_distance_all_agents` | Total system movement cost |

## Energy

| Metric | What it identifies |
|---|---|
| `total_energy_consumed` | Total resource cost of the run |
| `charging_time_fraction` | How much of fleet time is lost to charging overhead |
| `num_charging_events` | Charging frequency — frequent charging = agents running low, poor planning |
| `total_charging_timesteps` | Total productive capacity lost to charging |
| `avg_final_energy` / `min_final_energy` | Whether agents are dangerously depleted by end of run |

## Robustness

| Metric | What it identifies |
|---|---|
| `num_deadlocks` | Path planning failures — which algorithm creates harder-to-resolve traffic patterns? |

## Scalability

| Metric | What it identifies |
|---|---|
| `throughput_per_agent` | Efficiency per robot — does adding agents help equally across algorithms? |
