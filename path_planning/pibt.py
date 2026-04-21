from path_planning.base import PathPlanner
from path_planning.cooperative_astar import CooperativeAStar


class PIBT(PathPlanner):
    """
    Priority Inheritance with Backtracking (Okumura et al., 2019).
    https://doi.org/10.24963/ijcai.2019/76

    Greedy single-timestep planner: at each simulated step, agents are sorted
    by heuristic distance to goal (farther = higher priority) and each agent
    greedily claims its best available neighbor. Lower-priority agents that
    occupy the preferred cell are recursively displaced (priority inheritance).
    If displacement fails due to a cycle, the higher-priority agent falls back
    to the next candidate or waits (backtracking).

    Full paths are built by simulating max_plan_time steps and collecting the
    per-step positions into a trajectory — same format as all other planners.

    Complexity: O(T × n²) per planning call vs CA*'s O(n × G × T).
    Scales to 80–200 agents where CBS/PBS are impractical.

    Two-phase architecture (same as all planners):
      Phase 1 (_plan_charger_paths): PIBT simulation; paths reserved in CA* table.
      Phase 2 (_plan_task_paths):   PIBT simulation; CA* table checked read-only
                                     so charger reservations act as hard obstacles.
    """

    def __init__(self, grid_map):
        self.grid_map = grid_map
        self._ca = CooperativeAStar(grid_map)

    # ------------------------------------------------------------------
    # PathPlanner interface
    # ------------------------------------------------------------------

    def hold_position(self, position: tuple, agent_id: int,
                      current_timestep: int) -> None:
        """Reserve an idle agent's position in the CA* table."""
        self._ca.hold_position(position, agent_id, current_timestep)

    def _plan_charger_paths(self, agent_states: list, current_timestep: int,
                             max_plan_time: int) -> dict:
        """Plan paths for charger-bound agents using PIBT.

        Paths are reserved in the CA* table so task agents (Phase 2) route
        around charger agents via is_reserved checks in _pibt_step.
        """
        if not agent_states:
            return {}
        for state in agent_states:
            self._ca.clear_agent_reservations(state.agent_id)
        paths = self._pibt_simulate(agent_states, current_timestep, max_plan_time)
        for agent_id, path in paths.items():
            self._ca.reserve_path(path, agent_id, start_time=current_timestep)
        return paths

    def _plan_task_paths(self, agent_states: list, current_timestep: int,
                          max_plan_time: int) -> dict:
        """Plan paths for task agents using PIBT.

        Called after charger paths are already reserved in the CA* table.
        _pibt_step's is_reserved checks automatically route task agents
        around charger reservations and idle agents (hold_position).
        """
        if not agent_states:
            return {}
        for state in agent_states:
            self._ca.clear_agent_reservations(state.agent_id)
        paths = self._pibt_simulate(agent_states, current_timestep, max_plan_time)
        for agent_id, path in paths.items():
            self._ca.reserve_path(path, agent_id, start_time=current_timestep)
        return paths

    # ------------------------------------------------------------------
    # Core simulation
    # ------------------------------------------------------------------

    def _pibt_simulate(self, agent_states: list, current_timestep: int,
                        max_plan_time: int) -> dict:
        """Run PIBT for max_plan_time steps, building a full path per agent.

        Each step:
          1. Recompute priority ranks (farther from goal = higher priority;
             agents already at goal = highest priority so they are not displaced;
             agents with no goal = lowest priority).
          2. Process agents in priority order; each calls _pibt_step.
          3. Advance positions to claimed next positions.

        Returns dict mapping agent_id -> path (list of (x,y,z) tuples
        starting with the agent's current position, consistent with CA*).
        """
        agent_ids = [s.agent_id for s in agent_states]
        positions = {s.agent_id: s.get_position() for s in agent_states}
        goals     = {s.agent_id: s.get_current_goal() for s in agent_states}
        paths     = {s.agent_id: [s.get_position()] for s in agent_states}

        for step in range(max_plan_time):
            sim_t = current_timestep + step + 1

            priority_rank = self._compute_priority_ranks(agent_ids, positions, goals)
            sorted_agents = sorted(agent_ids, key=lambda aid: priority_rank[aid])

            next_pos   = {}  # agent_id → claimed next position
            cell_owner = {}  # position  → agent_id (inverse of next_pos)

            for agent_id in sorted_agents:
                if agent_id not in next_pos:
                    processing = set()  # fresh recursion-stack guard per top-level call
                    self._pibt_step(
                        agent_id, sim_t, positions, next_pos, cell_owner,
                        processing, goals, priority_rank,
                    )

            # Advance positions; fall back to staying if agent got no claim
            for agent_id in agent_ids:
                new_pos = next_pos.get(agent_id, positions[agent_id])
                positions[agent_id] = new_pos
                paths[agent_id].append(new_pos)

        return paths

    def _pibt_step(self, agent_id: int, sim_t: int,
                   positions: dict, next_pos: dict, cell_owner: dict,
                   processing: set, goals: dict, priority_rank: dict) -> bool:
        """Single-timestep PIBT move for one agent.

        Greedily picks the best available neighbor (lowest heuristic to goal),
        displacing lower-priority agents recursively when the preferred cell
        is occupied. Returns True if the agent successfully claims a cell.

        processing: recursion-stack guard — agents in this set are mid-chain
        and cannot be displaced further (prevents A→B→A infinite cycles).

        next_pos / cell_owner invariant: an entry exists iff the agent has
        committed to a position this step. Stale cell_owner entries (where
        next_pos[occupant] no longer points to that cell) are treated as free.
        """
        processing.add(agent_id)
        current = positions[agent_id]
        goal    = goals[agent_id]

        # Candidates: neighbors sorted by heuristic ascending, wait in place last
        neighbors = list(self.grid_map.get_neighbors(*current))
        if goal is not None:
            neighbors.sort(key=lambda p: self._ca.heuristic(p, goal))
        candidates = neighbors + [current]

        for candidate in candidates:
            # CA* reservation check: idle agents (hold_position) + charger paths
            if self._ca.is_reserved(*candidate, sim_t, agent_id):
                continue
            # Swap-conflict check (skip for wait-in-place)
            if candidate != current and self._ca.has_edge_conflict(
                    current, candidate, sim_t, agent_id):
                continue

            occupant = cell_owner.get(candidate)

            # Cell is free if unclaimed OR the cell_owner entry is stale
            # (stale = occupant already moved somewhere else this step)
            if occupant is None or next_pos.get(occupant) != candidate:
                next_pos[agent_id]    = candidate
                cell_owner[candidate] = agent_id
                return True

            # Cell genuinely claimed by occupant — try to displace if lower priority
            if (occupant not in processing
                    and priority_rank.get(occupant, len(priority_rank))
                        > priority_rank[agent_id]):
                if self._pibt_step(occupant, sim_t, positions, next_pos,
                                   cell_owner, processing, goals, priority_rank):
                    # Occupant moved away; claim the now-free cell
                    next_pos[agent_id]    = candidate
                    cell_owner[candidate] = agent_id
                    return True

        # All candidates exhausted — _pibt_simulate will keep agent at positions[agent_id]
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_priority_ranks(self, agent_ids: list, positions: dict,
                                  goals: dict) -> dict:
        """Assign integer ranks: 0 = highest priority.

        Order (highest → lowest):
          1. Agents already at their goal (never displaced — keeps task detection stable)
          2. Agents with a goal, sorted by heuristic distance descending (farther = higher)
          3. Agents with no goal (idle), sorted by agent_id

        Tiebreaker within group 2: agent_id ascending (deterministic, no oscillation).
        """
        at_goal   = []
        with_goal = []
        no_goal   = []

        for aid in agent_ids:
            g = goals[aid]
            if g is None:
                no_goal.append(aid)
            elif positions[aid] == g:
                at_goal.append(aid)
            else:
                with_goal.append((self._ca.heuristic(positions[aid], g), aid))

        # Farther from goal → higher priority; tiebreak by agent_id ascending
        with_goal.sort(key=lambda x: (-x[0], x[1]))

        ordered = sorted(at_goal) + [aid for _, aid in with_goal] + sorted(no_goal)
        return {aid: rank for rank, aid in enumerate(ordered)}