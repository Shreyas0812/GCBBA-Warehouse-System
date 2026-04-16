# Theoretical Complexity Analysis

Variables:
- `n` = number of agents
- `k` = number of tasks
- `r` = communication range (affects graph connectivity, not complexity class)

---

## GCBBA (Global Consensus-Based Bundle Algorithm)

**Per allocation call:**

1. **Bundle construction** — each agent scores all `k` tasks and greedily builds its bundle: `O(k)` per agent → `O(n · k)` total.
2. **Consensus phase** — agents broadcast their winning bids. Each agent broadcasts `O(k)` bid values to all `n-1` neighbors per round, for up to `n` rounds until convergence: `O(n · k)` work per round → `O(n² · k)` total for the consensus phase.
3. **Combined**: `O(n · k + n² · k)` = `O(n² · k)` total across all agents.

**Dominant term**: `O(n² · k)` — scales quadratically with agents and linearly with tasks.

**Note**: In practice, global consensus propagates through the communication graph over multiple rounds. Convergence rounds depend on graph diameter, so the constant factor varies with connectivity, but the worst-case complexity class remains the same.

---

## CBBA (Consensus-Based Bundle Algorithm)

**Per allocation call:**

1. **Bundle construction** — same as GCBBA: `O(n · k)`.
2. **Consensus phase** — CBBA uses a fixed broadcast protocol. Each agent broadcasts to all neighbors simultaneously. Convergence in `O(diameter)` rounds, each round `O(n · k)` work: `O(n² · k)` in the worst case (diameter = n).
3. **Combined**: `O(n² · k)`.

**Dominant term**: `O(n² · k)` — same class as GCBBA, but typically higher constant due to synchronous full broadcast vs gossip.

---

## SGA (Sequential Greedy Algorithm)

**Per allocation call:**

1. A single central agent (or coordinator) sorts all `n · k` agent-task pairs by score: `O(n · k · log(n · k))`.
2. Greedily assigns tasks in order, crossing off agent/task pairs as they are claimed: `O(n · k)`.
3. **No consensus rounds** — assignment is computed in one pass, then distributed.

**Combined**: `O(n · k · log(n · k))` dominated by the sort.

**Dominant term**: `O(n · k · log(n · k))` — better than GCBBA/CBBA for large `n`, but solution quality is lower and there is no decentralization.

**In `RunMetrics`**: `avg_consensus_rounds_per_call = 1` and `avg_convergence_iteration = 1` for SGA. The `avg_time_per_consensus_round_ms` will be high relative to GCBBA/CBBA because the single round includes the full greedy pass.

---

## Hungarian Algorithm (Offline Reference)

**Per task set:**

1. Constructs `n × k` cost matrix: `O(n · k)`.
2. Runs the Hungarian method (Kuhn-Munkres): `O(n³)` for square matrices; `O(n² · k)` for rectangular.

**Dominant term**: `O(n³)` for square case — optimal but centralized and not real-time feasible.

Used only as an offline quality reference. `solution_quality_ratio = our_makespan / hungarian_makespan` where 1.0 = optimal.

---

## Summary Table

| Method    | Per-call complexity | Rounds | Decentralized | Real-time feasible |
|-----------|--------------------|---------|--------------|--------------------|
| GCBBA     | O(n² · k)          | O(diam) | Yes          | Yes                |
| CBBA      | O(n² · k)          | O(diam) | Yes          | Yes                |
| SGA       | O(n·k·log(n·k))    | 1       | No           | Yes                |
| Hungarian | O(n³)              | N/A     | No           | No                 |

`diam` = diameter of the communication graph. At full connectivity, `diam = 1`.
