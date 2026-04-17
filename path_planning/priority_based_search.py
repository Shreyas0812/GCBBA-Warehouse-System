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

    def _pbs_plan(self, agent_states: list, current_timestep: int, max_time: int) -> dict:
        """Placeholder for PBS planning logic, which is shared between charger and task planning."""
        # If max_nodes is not set, compute it dynamically as n² (where n = number of agents being planned for).
        max_nodes = self.max_nodes or (len(agent_states) ** 2)
        return self._ca.plan_paths(agent_states, current_timestep, max_time, max_nodes)

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