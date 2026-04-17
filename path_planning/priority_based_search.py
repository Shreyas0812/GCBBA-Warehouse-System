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

