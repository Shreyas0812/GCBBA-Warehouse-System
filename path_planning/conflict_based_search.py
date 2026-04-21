import heapq

from path_planning.base import PathPlanner
from path_planning.cooperative_astar import CooperativeAStar


class ConflictBasedSearch(PathPlanner):
    """
    Conflict-Based Search (Sharon et al., 2015).
    "Conflict-based search for optimal multi-agent pathfinding."
    Artificial Intelligence, 219, 40-66.
    https://www.sciencedirect.com/science/article/pii/S0004370214001386

    Two-level algorithm:
      High level: searches a Constraint Tree (CT). Each CT node holds a set of
        per-agent constraints and a solution. When a conflict is found, two child
        nodes are created — one adding a constraint for agent i, one for agent j.
        CT nodes are ordered by sum-of-path-lengths (optimal = lowest cost first).
      Low level: per-agent time-extended A* that respects both the shared CA*
        reservation table (for idle agents and charger/task phase isolation) and
        its own explicit CBS constraints.

    Guarantees optimal sum-of-costs for static MAPF when no node budget is hit.
    max_nodes bounds the CT search to prevent runaway at lifelong-MAPF replan rates;
    defaults to n² (agents being planned for), same scaling rationale as PBS.
    """

    def __init__(self, grid_map, max_nodes: int = None):
        """
        Args:
            grid_map:   GridMap instance shared with the orchestrator.
            max_nodes:  CT node budget. Default None — computed as n² at each
                        planning call. Pass an explicit int to fix the budget.
        """
        self.grid_map  = grid_map
        self.max_nodes = max_nodes
        self._ca       = CooperativeAStar(grid_map)

    def hold_position(self, position: tuple, agent_id: int, current_timestep: int) -> None:
        """Reserve an idle agent's position in the CA* table so all planners avoid it."""
        self._ca.hold_position(position, agent_id, current_timestep)

    def _constrained_astar(
        self,
        start: tuple,
        goal: tuple,
        agent_id: int,
        constraints: frozenset,
        max_time: int,
        start_time: int,
    ) -> list | None:
        """Low-level solver: time-extended A* with explicit CBS constraints.

        Checks two layers of restrictions at each node:
          1. CA* reservation table — covers hold_position (idle agents) and
             charger paths reserved in Phase 1. Same checks as CA*'s solver.
          2. CBS constraints — per-agent vertex/edge constraints added by the
             high-level CT search for this specific agent.

        Constraint formats (elements of the constraints frozenset):
          ("vertex", agent_id, pos, t)         — agent cannot occupy pos at t
          ("edge",   agent_id, from, to, t)    — agent cannot move from→to at t

        Returns the shortest path as a list of (x,y,z) tuples, or None if the
        goal is unreachable within max_time under the given constraints.
        """
        if start == goal:
            return [start]
        if not self.grid_map.is_valid_cell(*start) or not self.grid_map.is_valid_cell(*goal):
            return None

        # Pre-index constraints for this agent so membership tests are O(1).
        # Only keep constraints that belong to agent_id.
        vertex_constraints = set()  # {(pos, t)}
        edge_constraints   = set()  # {(from_pos, to_pos, t)}
        for c in constraints:
            if c[1] != agent_id:
                continue
            if c[0] == "vertex":
                _, _, pos, t = c
                vertex_constraints.add((pos, t))
            elif c[0] == "edge":
                _, _, from_pos, to_pos, t = c
                edge_constraints.add((from_pos, to_pos, t))

        counter  = 0
        open_set = [(0, counter, (start, start_time), [start])]
        closed_set = set()

        while open_set:
            _, _, (current_pos, current_time), path = heapq.heappop(open_set)

            if (current_pos, current_time) in closed_set:
                continue
            if current_pos == goal:
                return path
            if current_time >= max_time:
                continue

            closed_set.add((current_pos, current_time))
            next_time = current_time + 1

            # --- Wait in place ---
            if (
                not self._ca.is_reserved(*current_pos, next_time, agent_id)
                and (current_pos, next_time) not in vertex_constraints
            ):
                path_new = path + [current_pos]
                g = len(path_new) - 1
                h = self._ca.heuristic(current_pos, goal)
                counter += 1
                heapq.heappush(open_set, (g + h, counter, (current_pos, next_time), path_new))

            # --- Move to each neighbor ---
            for neighbor in self.grid_map.get_neighbors(*current_pos):
                if (neighbor, next_time) in closed_set:
                    continue
                # CA* table checks (idle agents + charger reservation)
                if self._ca.is_reserved(*neighbor, next_time, agent_id):
                    continue
                if self._ca.has_edge_conflict(current_pos, neighbor, next_time, agent_id):
                    continue
                # CBS constraint checks
                if (neighbor, next_time) in vertex_constraints:
                    continue
                if (current_pos, neighbor, next_time) in edge_constraints:
                    continue

                path_new = path + [neighbor]
                g = len(path_new) - 1
                h = self._ca.heuristic(neighbor, goal)
                counter += 1
                heapq.heappush(open_set, (g + h, counter, (neighbor, next_time), path_new))

        return None  # goal unreachable within max_time under these constraints

    def _find_conflict(self, paths: dict) -> tuple | None:
        """Return the first conflict found across all agent pairs, or None.

        More detailed than PBS's version — CBS needs the position and timestep
        to build the right constraints for each child CT node.

        Returns:
          ("vertex", ai, aj, pos, t)           — both agents at pos at time t
          ("edge",   ai, aj, pos_i, pos_j, t)  — agents swap: i goes pos_i→pos_j
                                                  and j goes pos_j→pos_i at t

        Shorter paths are extended by holding at their last position (agent
        stays at goal indefinitely), matching reservation-table semantics.
        """
        agent_ids = list(paths.keys())
        for idx_i in range(len(agent_ids)):
            for idx_j in range(idx_i + 1, len(agent_ids)):
                ai, aj   = agent_ids[idx_i], agent_ids[idx_j]
                path_i   = paths[ai]
                path_j   = paths[aj]
                max_len  = max(len(path_i), len(path_j))

                for t in range(max_len):
                    pos_i = path_i[min(t, len(path_i) - 1)]
                    pos_j = path_j[min(t, len(path_j) - 1)]

                    # Vertex conflict
                    if pos_i == pos_j:
                        return ("vertex", ai, aj, pos_i, t)

                    # Edge (swap) conflict
                    if t > 0:
                        prev_i = path_i[min(t - 1, len(path_i) - 1)]
                        prev_j = path_j[min(t - 1, len(path_j) - 1)]
                        if pos_i == prev_j and pos_j == prev_i:
                            # Agents swap: at t-1 i was at prev_i, j at prev_j;
                            # at t they cross. Constrain the move at timestep t.
                            return ("edge", ai, aj, prev_i, prev_j, t)

        return None

    def _cbs_solve(self, agent_states: list, current_timestep: int, max_time: int) -> dict:
        """High-level CBS: best-first search over the Constraint Tree.

        Each CT node contains a frozenset of constraints and a full solution
        (one path per agent). Nodes are ordered by sum-of-path-lengths — the
        first conflict-free node popped is the optimal solution.

        Constraint building from a conflict:
          Vertex conflict (ai, aj, pos, t):
            Child 1 — ("vertex", ai, pos, t): ai cannot be at pos at t
            Child 2 — ("vertex", aj, pos, t): aj cannot be at pos at t
          Edge conflict (ai, aj, pos_i, pos_j, t):
            Child 1 — ("edge", ai, pos_i, pos_j, t): ai cannot go pos_i→pos_j at t
            Child 2 — ("edge", aj, pos_j, pos_i, t): aj cannot go pos_j→pos_i at t

        Only the constrained agent is replanned per child — all other paths
        are inherited unchanged, keeping the cost delta minimal.

        Falls back to last-popped paths if node_budget is exhausted. Unlike PBS,
        no CA* table fix-up needed here — _constrained_astar only reads the table
        (never writes), so there is no stale reservation state to correct.
        """
        n           = len(agent_states)
        node_budget = self.max_nodes if self.max_nodes is not None else n * n
        id_to_state = {s.agent_id: s for s in agent_states}

        # Root node: each agent plans independently with no CBS constraints.
        root_constraints = frozenset()
        root_paths       = {}
        for state in agent_states:
            path = self._constrained_astar(
                start=state.get_position(), goal=state.get_current_goal(),
                agent_id=state.agent_id, constraints=root_constraints,
                max_time=max_time, start_time=current_timestep,
            )
            root_paths[state.agent_id] = path if path is not None else [state.get_position()]

        root_cost  = sum(len(p) for p in root_paths.values())
        node_id    = 0
        heap       = [(root_cost, node_id, root_constraints, root_paths)]
        last_paths = root_paths
        nodes_expanded = 0

        while heap and nodes_expanded < node_budget:
            _, _, constraints, paths = heapq.heappop(heap)
            nodes_expanded += 1
            last_paths = paths

            conflict = self._find_conflict(paths)
            if conflict is None:
                return paths  # optimal conflict-free solution found

            # Build constraint pairs for the two child nodes.
            if conflict[0] == "vertex":
                _, ai, aj, pos, t = conflict
                branches = [
                    (ai, frozenset([*constraints, ("vertex", ai, pos, t)])),
                    (aj, frozenset([*constraints, ("vertex", aj, pos, t)])),
                ]
            else:  # "edge"
                _, ai, aj, pos_i, pos_j, t = conflict
                branches = [
                    (ai, frozenset([*constraints, ("edge", ai, pos_i, pos_j, t)])),
                    (aj, frozenset([*constraints, ("edge", aj, pos_j, pos_i, t)])),
                ]

            for constrained_agent, new_constraints in branches:
                state    = id_to_state[constrained_agent]
                new_path = self._constrained_astar(
                    start=state.get_position(), goal=state.get_current_goal(),
                    agent_id=constrained_agent, constraints=new_constraints,
                    max_time=max_time, start_time=current_timestep,
                )
                if new_path is None:
                    new_path = [state.get_position()]

                new_paths = dict(paths)          # copy; only this agent's path changes
                new_paths[constrained_agent] = new_path
                new_cost = sum(len(p) for p in new_paths.values())
                node_id += 1
                heapq.heappush(heap, (new_cost, node_id, new_constraints, new_paths))

        # node_budget exhausted — return last-popped node's paths.
        # No CA* table fix-up needed: _constrained_astar is read-only on the
        # table, so no stale state accumulates (unlike PBS's push-time writes).
        return last_paths

    def _plan_charger_paths(self, agent_states: list, current_timestep: int,
                             max_plan_time: int) -> dict:
        """Plan paths for agents navigating to a charger using CBS.

        Clears stale CA* reservations for these agents first, then runs CBS.
        The winning paths are reserved in the CA* table so that task agents
        (Phase 2) route around them via _constrained_astar's is_reserved checks.
        """
        if not agent_states:
            return {}
        # Clear stale reservations from the previous timestep so they don't
        # incorrectly block the low-level solver's CA* table reads.
        for state in agent_states:
            self._ca.clear_agent_reservations(state.agent_id)
        max_time = current_timestep + max_plan_time
        paths = self._cbs_solve(agent_states, current_timestep, max_time)
        # Reserve charger paths so task agents plan around them in Phase 2.
        for agent_id, path in paths.items():
            self._ca.reserve_path(path, agent_id, start_time=current_timestep)
        return paths

    def _plan_task_paths(self, agent_states: list, current_timestep: int,
                          max_plan_time: int) -> dict:
        """Plan paths for task agents using CBS.

        Called after charger paths are already reserved in the CA* table, so
        _constrained_astar automatically routes task agents around chargers.
        No reservation needed at the end — this is the final planning phase.
        """
        if not agent_states:
            return {}
        for state in agent_states:
            self._ca.clear_agent_reservations(state.agent_id)
        max_time = current_timestep + max_plan_time
        return self._cbs_solve(agent_states, current_timestep, max_time)
