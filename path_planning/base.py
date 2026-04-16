from abc import ABC, abstractmethod


class PathPlanner(ABC):
    """Abstract base class for multi-agent path planners.

    All internals (reservation tables, constraint trees, etc.) are managed
    inside each concrete implementation. The orchestrator only calls plan_all().
    """

    @abstractmethod
    def plan_all(
        self,
        agent_states: list,
        current_timestep: int,
        max_plan_time: int,
    ) -> dict:
        """Plan collision-free paths for a set of agents.

        Args:
            agent_states: agents that need a new path (needs_new_path=True).
            current_timestep: current simulation timestep.
            max_plan_time: maximum number of future timesteps to search.

        Returns:
            dict mapping agent_id -> path (list of (x,y,z) tuples).
            If no path is found for an agent, maps to [agent_start_pos].
        """
        pass