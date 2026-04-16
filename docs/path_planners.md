# Path Planners

All planners implement the `PathPlanner` ABC (`path_planning/base.py`) and are selected via the
`path_planner` config key. Each exposes `plan_all()` and `hold_position()` — the orchestrator
never calls planner internals directly.

---

## Implemented

### Cooperative A* (`ca_star`)
**File:** `path_planning/cooperative_astar.py` · **Class:** `CooperativeAStar`

Priority-based sequential planning in a time-expanded space-time graph. Agents are planned one
at a time in a shuffled order; each agent's path is added to a shared reservation table before
the next agent plans. Later agents route around earlier ones.

- **Completeness:** Yes (with wait-in-place)
- **Optimality:** No — first agent gets optimal path, others detour
- **Scalability:** Degrades with many agents (reservation table grows; `max_plan_time` exhaustion)
- **Key params:** `max_plan_time` (search horizon, default 400)

---

## Planned

### Conflict-Based Search (`cbs`)
**File:** `path_planning/conflict_based_search.py` · **Class:** `ConflictBasedSearch`

Two-level search: high-level constraint tree (CT) resolves conflicts between pairs of agents;
low-level single-agent A* replans under added constraints. Finds **optimal** conflict-free paths.

- **Completeness:** Yes
- **Optimality:** Yes (sum-of-costs)
- **Scalability:** Exponential worst-case; practical up to ~20–30 agents
- **Reference:** Sharon et al., 2015

---

### Enhanced CBS (`ecbs`)
**File:** `path_planning/enhanced_cbs.py` · **Class:** `EnhancedCBS`

Bounded-suboptimal CBS with inflation factor ε. Uses focal search to find solutions within
(1+ε)× optimal. Significantly faster than CBS at the cost of optimality guarantee.

- **Completeness:** Yes
- **Optimality:** Bounded suboptimal (1+ε)
- **Scalability:** Better than CBS; practical up to ~50 agents
- **Reference:** Barer et al., 2014

---

### Priority-Based Search (`pbs`)
**File:** `path_planning/priority_based_search.py` · **Class:** `PriorityBasedSearch`

Builds a priority ordering on-the-fly using depth-first search over the priority tree. Simpler
than CBS — no constraint tree, just re-plans lower-priority agents to avoid higher-priority ones.
Sits between CA* and CBS in complexity and solution quality.

- **Completeness:** Yes (complete under the priority ordering found)
- **Optimality:** No
- **Scalability:** Good — faster than CBS, better than CA* quality
- **Reference:** Ma et al., 2019

---

### Rolling Horizon Collision Resolution (`rhcr`)
**File:** `path_planning/rhcr.py` · **Class:** `RHCR`

Designed for **lifelong/online** MAPF (the exact setting of this warehouse simulation). Runs
CBS/ECBS over a short rolling time window `w`; replans every `h` timesteps. Agents outside the
window follow their last committed path. Balances plan quality with replan frequency.

- **Completeness:** Yes (within window)
- **Optimality:** Within window
- **Scalability:** Excellent — decouples planning horizon from agent count
- **Best fit for:** This simulation (lifelong, continuous task injection)
- **Key params:** window size `w`, replan interval `h`
- **Reference:** Li et al., 2021 — *Lifelong Multi-Agent Path Finding in Large-Scale Warehouses*

---

## Selection

Set `path_planner` in the orchestrator constructor or experiment config:

```python
IntegrationOrchestrator(
    config_path="...",
    path_planner="ca_star",   # "ca_star" | "cbs" | "ecbs" | "pbs" | "rhcr"
)
```

## Complexity comparison

| Planner | Time complexity | Quality | Best for |
|---|---|---|---|
| CA* | O(w·b^d) per agent | Suboptimal | Baseline, fast |
| PBS | O(n · w·b^d) | Suboptimal, better | Medium density |
| CBS | O(2^n · w·b^d) | Optimal | Low agent count |
| ECBS | O(2^n · w·b^d / ε) | (1+ε)-optimal | Medium agent count |
| RHCR | O(CBS over window) | Window-optimal | Lifelong MAPF |

`n` = agents, `w` = window/horizon, `b` = branching factor, `d` = path depth