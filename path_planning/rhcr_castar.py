from tqdm import tqdm

from path_planning.base import PathPlanner
from path_planning.cooperative_astar import CooperativeAStar


class RHCRCAStar(PathPlanner):
    """
    Rolling Horizon Collision Resolution with Cooperative A* inner solver.
    (Li et al., 2021) https://arxiv.org/abs/2005.07371

    Instead of planning a full path to the goal, plans only `window_size` (w)
    timesteps ahead. Agents execute `replanning_period` (h) steps then replan,
    creating a natural rolling horizon without any orchestrator changes.

    Inner solver: Cooperative A* (sequential priority-based). Full RHCR uses
    CBS as the inner solver; CA* is a valid simplification noted in the thesis.
    See rhcr_cbs.py (to be implemented) for the CBS variant.
    """

    def __init__(self, grid_map, window_size: int = 20, replanning_period: int = None):
        """
        Args:
            grid_map:           GridMap instance shared with the orchestrator.
            window_size:        How many timesteps ahead to plan (w in the paper).
                                Default 20 -- on a 30x30 map (max BFS dist ~60) this
                                means ~3 replans per trip, giving fresh conflict
                                resolution without excessive planning overhead.
            replanning_period:  How many steps to execute before replanning (h in the paper).
                                Must be <= window_size. Defaults to window_size (h = w),
                                meaning agents replan only when the window is exhausted.
                                Set h < w to replan more frequently (e.g. h=5, w=20).
        """
        if replanning_period is not None and replanning_period > window_size:
            raise ValueError(f"replanning_period ({replanning_period}) must be <= window_size ({window_size})")
        self.grid_map          = grid_map
        self.window_size       = window_size
        self.replanning_period = replanning_period if replanning_period is not None else window_size
        self._ca               = CooperativeAStar(grid_map)

    def hold_position(self, position: tuple, agent_id: int, current_timestep: int) -> None:
        """Delegate to CA*'s reservation table — no RHCR-specific logic needed."""
        self._ca.hold_position(position, agent_id, current_timestep)

    def _plan_charger_paths(self, agent_states: list, current_timestep: int, _max_plan_time: int) -> dict:
        """Plan paths for agents navigating to a charger, capped to window_size steps.

        _max_plan_time is ignored — RHCR always uses window_size so the rolling
        horizon applies to charger trips too.
        """
        result   = {}
        max_time = current_timestep + self.window_size
        for agent_state in agent_states:
            self._ca.clear_agent_reservations(agent_state.agent_id)
            start = agent_state.get_position()
            goal  = agent_state.get_current_goal()
            path  = self._ca.plan_path_with_reservations(
                start=start, goal=goal, agent_id=agent_state.agent_id,
                max_time=max_time, start_time=current_timestep,
                require_goal=False,
            )
            if path is None:
                tqdm.write(f"[t={current_timestep}] Agent {agent_state.agent_id}: "
                           f"RHCR found no charger path within window={self.window_size} — staying in place")
                path = [start]
            self._ca.reserve_path(path, agent_state.agent_id, start_time=current_timestep)
            result[agent_state.agent_id] = path[:self.replanning_period]  # execute only h steps
        return result

    def _plan_idle_paths(self, agent_states: list, current_timestep: int, _max_plan_time: int) -> dict:
        """Plan paths for agents navigating to idle-task stations, capped to window_size steps.

        Wait agents plan after chargers but before task agents, giving them
        priority to clear out of eject zones quickly. _max_plan_time is ignored —
        RHCR always uses window_size.
        """
        result   = {}
        max_time = current_timestep + self.window_size
        for agent_state in agent_states:
            self._ca.clear_agent_reservations(agent_state.agent_id)
            start = agent_state.get_position()
            goal  = agent_state.get_current_goal()
            path  = self._ca.plan_path_with_reservations(
                start=start, goal=goal, agent_id=agent_state.agent_id,
                max_time=max_time, start_time=current_timestep,
                require_goal=False,
            )
            if path is None:
                tqdm.write(f"[t={current_timestep}] Agent {agent_state.agent_id}: "
                           f"RHCR found no wait path within window={self.window_size} — staying in place")
                path = [start]
            self._ca.reserve_path(path, agent_state.agent_id, start_time=current_timestep)
            result[agent_state.agent_id] = path[:self.replanning_period]  # execute only h steps
        return result

    def _plan_task_paths(self, agent_states: list, current_timestep: int, _max_plan_time: int) -> dict:
        """Plan paths for task agents, capped to window_size steps.

        _max_plan_time is ignored — same rolling horizon applies as for charger paths.
        Called after charger paths are already reserved, so task agents route around them.
        """
        result   = {}
        max_time = current_timestep + self.window_size
        for agent_state in agent_states:
            self._ca.clear_agent_reservations(agent_state.agent_id)
            start = agent_state.get_position()
            goal  = agent_state.get_current_goal()
            path  = self._ca.plan_path_with_reservations(
                start=start, goal=goal, agent_id=agent_state.agent_id,
                max_time=max_time, start_time=current_timestep,
                require_goal=False,
            )
            if path is None:
                tqdm.write(f"[t={current_timestep}] Agent {agent_state.agent_id}: "
                           f"RHCR found no path within window={self.window_size} — staying in place")
                path = [start]
            self._ca.reserve_path(path, agent_state.agent_id, start_time=current_timestep)
            result[agent_state.agent_id] = path[:self.replanning_period]  # execute only h steps
        return result