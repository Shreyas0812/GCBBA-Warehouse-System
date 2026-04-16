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
- **Reference:** Silver, D. (2005). *Cooperative Pathfinding*. AIIDE 2005.
  https://www.davidsilver.uk/wp-content/uploads/2020/03/coop-path-AIIDEf.pdf

---

## Planned (implementation order)

> **RHCR → PBS → CBS → ECBS**
>
> RHCR is the state-of-the-art for steady-state (lifelong) MAPF and is implemented first.
> PBS and CBS follow as comparison baselines. ECBS is the state-of-the-art for batch MAPF
> and is implemented last as it builds on CBS.

### Rolling Horizon Collision Resolution (`rhcr`) — **SotA: steady-state/lifelong MAPF**
**File:** `path_planning/rhcr.py` · **Class:** `RHCR` · **Status:** Next to implement

Designed for **lifelong/online** MAPF (the exact setting of this warehouse simulation). Runs
CBS/ECBS over a short rolling time window `w`; replans every `h` timesteps. Agents outside the
window follow their last committed path. Balances plan quality with replan frequency.

- **Completeness:** Yes (within window)
- **Optimality:** Within window
- **Scalability:** Excellent — decouples planning horizon from agent count
- **Best fit for:** Steady-state continuous task injection (this simulation's primary mode)
- **Key params:** window size `w`, replan interval `h`
- **Reference:** Li, J., Chen, Z., Harabor, D., Stuckey, P. J., & Koenig, S. (2021).
  *Lifelong Multi-Agent Path Finding in Large-Scale Warehouses*. AAAI 2021.
  https://arxiv.org/abs/2005.07371

---

### Priority-Based Search (`pbs`)
**File:** `path_planning/priority_based_search.py` · **Class:** `PriorityBasedSearch` · **Status:** After RHCR

Builds a priority ordering on-the-fly using depth-first search over the priority tree. Simpler
than CBS — no constraint tree, just re-plans lower-priority agents to avoid higher-priority ones.
Sits between CA* and CBS in complexity and solution quality.

- **Completeness:** Yes (complete under the priority ordering found)
- **Optimality:** No
- **Scalability:** Good — faster than CBS, better quality than CA*
- **Reference:** Ma, H., Harabor, D., Stuckey, P. J., Li, J., & Koenig, S. (2019).
  *Searching with Consistent Prioritization for Multi-Agent Path Finding*. AAAI 2019.
  https://arxiv.org/abs/1901.11282

---

### Conflict-Based Search (`cbs`)
**File:** `path_planning/conflict_based_search.py` · **Class:** `ConflictBasedSearch`

Two-level search: high-level constraint tree (CT) resolves conflicts between pairs of agents;
low-level single-agent A* replans under added constraints. Finds **optimal** conflict-free paths.

- **Completeness:** Yes
- **Optimality:** Yes (sum-of-costs)
- **Scalability:** Exponential worst-case; practical up to ~20–30 agents
- **Reference:** Sharon, G., Stern, R., Felner, A., & Sturtevant, N. R. (2015).
  *Conflict-Based Search for Optimal Multi-Agent Pathfinding*. Artificial Intelligence, 219, 40–66.
  https://doi.org/10.1016/j.artint.2014.11.006

---

### Enhanced CBS (`ecbs`) — **SotA: batch MAPF (planned)**
**File:** `path_planning/enhanced_cbs.py` · **Class:** `EnhancedCBS` · **Status:** After CBS

Bounded-suboptimal CBS with inflation factor ε. Uses focal search to find solutions within
(1+ε)× optimal. Significantly faster than CBS at the cost of optimality guarantee.

- **Completeness:** Yes
- **Optimality:** Bounded suboptimal (1+ε)
- **Scalability:** Better than CBS; practical up to ~50 agents
- **Reference:** Barer, M., Sharon, G., Stern, R., & Felner, A. (2014).
  *Suboptimal Variants of the Conflict-Based Search Algorithm for the Multi-Agent Pathfinding Problem*. SOCS 2014.
  https://ojs.aaai.org/index.php/SOCS/article/view/18315

#### More recent batch SotA (time permitting)

**EECBS** (`eecbs`) — Explicit Estimation CBS (Li et al., 2022). Replaces the focal heuristic
with an explicit estimate of the true conflict cost, giving much tighter suboptimality bounds
in practice. Strictly better than ECBS; drop-in replacement.
- **Reference:** Li, J., et al. (2022). *Explicit Estimation for Bounded Suboptimal Multi-Agent Path Finding*. IJCAI 2022.
  https://arxiv.org/abs/2204.07848

**LaCAM** (`lacam`) — Large-scale Collision Avoidance with Machine learning (Okumura, 2023).
Complete, very fast (~1ms for 1000 agents), trades optimality for speed. Not CBS-based —
uses lazy constraint addition. Best suited for extremely large agent counts.
- **Reference:** Okumura, K. (2023). *LaCAM: Search-Based Algorithm for Quick Multi-Agent Pathfinding*. IJCAI 2023.
  https://arxiv.org/abs/2301.02120

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

| Planner | Time complexity | Quality | Best for | SotA |
|---|---|---|---|---|
| CA* | O(w·b^d) per agent | Suboptimal | Baseline, fast | — |
| PBS | O(n · w·b^d) | Suboptimal, better | Medium density | — |
| CBS | O(2^n · w·b^d) | Optimal | Low agent count | — |
| ECBS | O(2^n · w·b^d / ε) | (1+ε)-optimal | Batch MAPF | **Batch** |
| RHCR | O(CBS over window) | Window-optimal | Lifelong MAPF | **Steady-state** |
| EECBS | O(2^n · w·b^d / ε) | Tighter (1+ε) | Batch MAPF | **Batch (2022)** |
| LaCAM | O(n · d) | Suboptimal | Very large n | **Scale (2023)** |

`n` = agents, `w` = window/horizon, `b` = branching factor, `d` = path depth