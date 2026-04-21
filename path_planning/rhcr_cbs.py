from path_planning.base import PathPlanner
from path_planning.conflict_based_search import ConflictBasedSearch


class RHCRCBSStar(PathPlanner):
    """
    Rolling Horizon Collision Resolution with CBS inner solver.
    (Li et al., 2021) https://arxiv.org/abs/2005.07371

    This is the full RHCR as described in the original paper — CBS (rather than
    CA*) is used as the inner solver within each rolling window. CBS finds
    optimal (minimum sum-of-costs) conflict-free paths within the window,
    whereas RHCR+CA* uses a greedy sequential ordering.

    window_size (w): how many timesteps ahead to plan.
    replanning_period (h): how many steps agents execute before replanning.
    Must satisfy h <= w. Defaults to h = w (replan only when window exhausted).

    See rhcr_castar.py for the CA* inner solver variant.
    """

    def __init__(self, grid_map, window_size: int = 20,
                 replanning_period: int = None, max_nodes: int = None):
        """
        Args:
            grid_map:           GridMap instance shared with the orchestrator.
            window_size:        How many timesteps ahead to plan (w).
            replanning_period:  Steps to execute before replanning (h <= w).
                                Defaults to window_size (h = w).
            max_nodes:          CBS CT node budget per planning call.
                                Defaults to n² (agents being planned for).
        """
        if replanning_period is not None and replanning_period > window_size:
            raise ValueError(
                f"replanning_period ({replanning_period}) must be <= window_size ({window_size})"
            )
        self.grid_map          = grid_map
        self.window_size       = window_size
        self.replanning_period = replanning_period if replanning_period is not None else window_size
        self._cbs              = ConflictBasedSearch(grid_map, max_nodes=max_nodes)

    def hold_position(self, position: tuple, agent_id: int, current_timestep: int) -> None:
        """Delegate to CBS's CA* table — no RHCR-specific logic needed."""
        self._cbs.hold_position(position, agent_id, current_timestep)

    def _plan_charger_paths(self, agent_states: list, current_timestep: int,
                             _max_plan_time: int) -> dict:
        """Plan charger paths within the rolling window using CBS.

        _max_plan_time is ignored — RHCR always uses window_size so the rolling
        horizon applies to charger trips too.
        """
        if not agent_states:
            return {}
        for state in agent_states:
            self._cbs._ca.clear_agent_reservations(state.agent_id)
        max_time = current_timestep + self.window_size
        paths = self._cbs._cbs_solve(agent_states, current_timestep, max_time)
        # Reserve charger paths so task agents route around them in Phase 2.
        for agent_id, path in paths.items():
            self._cbs._ca.reserve_path(path, agent_id, start_time=current_timestep)
        return {aid: p[:self.replanning_period] for aid, p in paths.items()}

    def _plan_task_paths(self, agent_states: list, current_timestep: int,
                          _max_plan_time: int) -> dict:
        """Plan task paths within the rolling window using CBS.

        Called after charger paths are already reserved, so CBS routes task
        agents around both charger reservations and each other.
        """
        if not agent_states:
            return {}
        for state in agent_states:
            self._cbs._ca.clear_agent_reservations(state.agent_id)
        max_time = current_timestep + self.window_size
        paths = self._cbs._cbs_solve(agent_states, current_timestep, max_time)
        return {aid: p[:self.replanning_period] for aid, p in paths.items()}