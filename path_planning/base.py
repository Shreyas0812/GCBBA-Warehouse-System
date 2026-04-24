from abc import ABC, abstractmethod


class PathPlanner(ABC):
    """Abstract base class for multi-agent path planners.

    Subclasses implement _plan_charger_paths() and _plan_task_paths()
    independently, allowing different algorithms for each phase.
    The orchestrator only calls plan_all() and hold_position().
    """

    def plan_all(
        self,
        agent_states: list,
        current_timestep: int,
        max_plan_time: int,
        planner_map: dict = None,
    ) -> dict:
        """Concrete three-phase entry point. Do not override in subclasses.

        agent_states are pre-filtered by the orchestrator (needs_new_path=True,
        goal is not None). is_navigating_to_charger and is_navigating_to_wait
        are set by AgentState.

        Phase 1: charger agents plan first and reserve their paths.
        Phase 2: wait-station agents plan and reserve their paths.
        Phase 3: task agents plan around the reserved charger and wait paths.

        Args:
            agent_states: List of AgentState objects needing paths.
            current_timestep: Current simulation timestep.
            max_plan_time: Maximum planning horizon.
            planner_map: Optional dict mapping phase names to PathPlanner instances.
                Keys: "charger", "idle", "task". If None, uses self for all phases.
                Example: {"charger": ca_star, "idle": ca_star, "task": rhcr}

        Returns:
            dict mapping agent_id -> path (list of (x,y,z) tuples).
        """
        charger_agents = [a for a in agent_states if a.is_navigating_to_charger]
        wait_agents    = [a for a in agent_states if a.is_navigating_to_wait]
        task_agents    = [a for a in agent_states if not a.is_navigating_to_charger and not a.is_navigating_to_wait]

        # Use provided planners or fall back to self (default: single-planner mode)
        charger_planner = planner_map["charger"] if planner_map else self
        idle_planner    = planner_map["idle"] if planner_map else self
        task_planner    = planner_map["task"] if planner_map else self

        paths = charger_planner._plan_charger_paths(charger_agents, current_timestep, max_plan_time)
        paths.update(idle_planner._plan_idle_paths(wait_agents, current_timestep, max_plan_time))
        paths.update(task_planner._plan_task_paths(task_agents, current_timestep, max_plan_time))
        return paths

    @abstractmethod
    def _plan_charger_paths(
        self,
        agent_states: list,
        current_timestep: int,
        max_plan_time: int,
    ) -> dict:
        """Plan paths for agents navigating to a charger.

        Must reserve paths internally before returning so that
        _plan_idle_paths() and _plan_task_paths() route around them.

        Returns:
            dict mapping agent_id -> path (list of (x,y,z) tuples).
            If no path is found, maps to [agent_start_pos].
        """
        pass

    @abstractmethod
    def _plan_idle_paths(
        self,
        agent_states: list,
        current_timestep: int,
        max_plan_time: int,
    ) -> dict:
        """Plan paths for agents navigating to idle-task (wait) stations.

        Called after charger paths are reserved. Must reserve paths internally
        so task agents route around them. These agents have high priority to
        avoid blocking critical paths while waiting for task assignments.

        Returns:
            dict mapping agent_id -> path (list of (x,y,z) tuples).
            If no path is found, maps to [agent_start_pos].
        """
        pass

    @abstractmethod
    def _plan_task_paths(
        self,
        agent_states: list,
        current_timestep: int,
        max_plan_time: int,
    ) -> dict:
        """Plan paths for agents completing warehouse tasks.

        Called after charger paths are already reserved. Implementations
        may use any algorithm (CA*, CBS, PBS, RHCR, etc.).

        Returns:
            dict mapping agent_id -> path (list of (x,y,z) tuples).
            If no path is found, maps to [agent_start_pos].
        """
        pass

    @abstractmethod
    def hold_position(
        self,
        position: tuple,
        agent_id: int,
        current_timestep: int,
    ) -> None:
        """Reserve an agent's current position without planning a new path.

        Called for idle agents (goal=None) so other agents plan around them.
        Implementations without a shared reservation table (e.g. CBS) may
        treat this as a no-op.
        """
        pass