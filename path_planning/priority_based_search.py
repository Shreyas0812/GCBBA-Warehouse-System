from tqdm import tqdm

from path_planning.base import PathPlanner
from path_planning.cooperative_astar import CooperativeAStar


class PriorityBasedSearch(PathPlanner):
    """
    Priority-Based Search (Ma et al., 2019).
    https://arxiv.org/abs/1812.06356

    Searches over priority orderings using DFS instead of committing to a
    fixed random order like CA*. When two agents conflict, PBS branches into
    two child nodes — one where agent A has priority over B, one where B has
    priority over A — and replans the lower-priority agent. This makes PBS
    complete over the space of priority orderings.

    Single-agent solver: CA*'s plan_path_with_reservations (same as CA* and RHCR).
    max_nodes bounds the DFS tree to prevent runaway search at runtime; defaults
    to n² (agents being planned for) so the budget scales automatically across maps.
    """

    def __init__(self, grid_map, max_nodes: int = None):
        """
        Args:
            grid_map:   GridMap instance shared with the orchestrator.
            max_nodes:  Maximum PBS tree nodes to expand before falling back
                        to the last explored paths. Default None — computed
                        dynamically as n² (where n = number of agents being
                        planned for) at each call. Node Budget is necessary 
                        to prevent PBS from running indefinitely at runtime, 
                        but setting it too low can cause suboptimal paths.
        """
        self.grid_map  = grid_map
        self.max_nodes = max_nodes
        self._ca       = CooperativeAStar(grid_map)

    def hold_position(self, position: tuple, agent_id: int, current_timestep: int) -> None:
        """Delegate to CA*'s reservation table — no PBS-specific logic needed."""
        self._ca.hold_position(position, agent_id, current_timestep)

    def _topological_sort(self, priorities: set, agent_states: list) -> list:
        """Return agent_states in an order consistent with the given priority constraints.
        
        Kahn's algorithm: iteratively add agents with no incoming edges to the ordering and remove their outgoing edges until all agents are ordered or a cycle is detected.

        Agents with no priority constraints can be ordered arbitrarily
        """
        ids = [s.agent_id for s in agent_states]
        id_to_state = {s.agent_id: s for s in agent_states}

        in_degree = {agent_id: 0 for agent_id in ids}
        graph = {agent_id: [] for agent_id in ids}

        for higher, lower in priorities:
            if higher in graph and lower in graph:
                graph[higher].append(lower)
                in_degree[lower] += 1
        
        queue = [agent_id for agent_id in ids if in_degree[agent_id] == 0]
        result = []
        while queue:
            current_agent_id = queue.pop(0)
            result.append(id_to_state[current_agent_id])
            for neighbor in graph[current_agent_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # Safety: if result doesn't contain all agents, it means there's a cycle. In that case, we can return the partial ordering and let PBS detect the cycle later.
        planned = {s.agent_id for s in result}
        for s in agent_states:
            if s.agent_id not in planned:
                result.append(s)

        return result

    def _plan_with_priorities(self, agent_states: list, priorities: set, current_timestep: int, max_time: int) -> dict:
        """Plan paths for agents given a set of priority orderings.

        Clears each agent's prior reservations then re-plans sequentially:
        higher-priority agents reserve first, lower-priority agents route
        around them.

        sequential CA* loop as CooperativeAStar,
        but with the order determined by PBS priorities rather than random shuffle.
        """
        order = self._topological_sort(priorities, agent_states)

        # Clear reservations for all agents being planned for, since we'll re-plan them in a new order. This also ensures that any agents not included in the current PBS node (e.g. because of a cycle) won't have their reservations accidentally preserved.
        for agent_state in agent_states:
            self._ca.clear_reservations(agent_state.agent_id)

        paths = {}
        for agent_state in order:
            start = agent_state.get_position()
            goal = agent_state.get_current_goal()
            path = self._ca.plan_path_with_reservations(start=start, goal=goal, agent_id=agent_state.agent_id, max_time=max_time, start_time=current_timestep)

            if path is None:
                path = [start]

            self._ca.reserve_path(path, agent_state.agent_id, start_time=current_timestep)
            paths[agent_state.agent_id] = path

        return paths

    def _pbs_plan(self, agent_states: list, current_timestep: int, max_time: int) -> dict:
        """Core PBS logic: DFS over priority orderings.

        Start: Unconstrained root node, detect conflicts, and branch on the first
        conflict by creating two child nodes with opposite priority orderings for the
        conflicting agents. 
        
        Replan the lower-priority agent in each child node using CA* with the new
        constraints. Continue until a conflict-free set of paths is found or max_nodes is
        reached.
        """

        n = len(agent_states)
        node_budget = self.max_nodes if self.max_nodes is not None else n**2
        root_paths = self._plan_with_priorities(agent_states, set(), current_timestep, max_time)



    def _plan_charger_paths(self, agent_states: list, current_timestep: int,
                             max_plan_time: int) -> dict:
        """Plan paths for agents navigating to a charger using PBS.

        Charger agents plan first so task agents route around them.
        max_time is bounded by max_plan_time (not windowed like RHCR).
        """
        if not agent_states:
            return {}
        max_time = current_timestep + max_plan_time
        return self._pbs_plan(agent_states, current_timestep, max_time)

    def _plan_task_paths(self, agent_states: list, current_timestep: int,
                          max_plan_time: int) -> dict:
        """Plan paths for task agents using PBS.

        Called after charger paths are already reserved, so PBS routes task
        agents around both charger reservations and each other.
        """
        if not agent_states:
            return {}
        max_time = current_timestep + max_plan_time
        return self._pbs_plan(agent_states, current_timestep, max_time)