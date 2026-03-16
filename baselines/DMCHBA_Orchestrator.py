"""
DMCHBA (Distributed Matching-by-Clones Hungarian-Based Algorithm) Orchestrator
for warehouse task allocation.
 
SOTA baseline from Samiei & Sun (IEEE T-RO 2024).
 
Algorithm overview:
  1. Clone agents: each real agent i gets ceil(N_t / N_a) clones,
     producing a square cost matrix of ~N_t x N_t.
  2. Build cost matrix: each clone's cost to every task is computed
     using BFS distances (same as LCBA/CBBA/SGA).
  3. Hungarian assignment: each agent independently solves the
     assignment problem on the cost matrix (with identical info,
     they converge to the same solution).
  4. TSP ordering: each real agent collects tasks assigned to its
     clones and solves a local TSP via 2-opt to order execution.
 
Communication model:
  - On a fully connected graph: all agents exchange costs and run
    Hungarian on the same matrix -> identical assignments.
  - On a disconnected graph: each connected component independently
    builds its own cost matrix (clones + tasks visible within the
    component) and runs Hungarian separately. Tasks not reachable
    by any component remain unassigned.

Should perform really well for batch task allocation with many tasks and few agents, 
as the Hungarian algorithm optimally solves the assignment problem. 

It may struggle with dynamic task arrivals or when communication is limited, 
as the cost matrix may become outdated or incomplete.
 
Interface matches GCBBA_Orchestrator for drop-in replacement.
"""

import time
import numpy as np
import networkx as nx
from math import ceil
from scipy.optimize import linear_sum_assignment

from gcbba.GCBBA_Task import GCBBA_Task


class DMCHBA_Orchestrator:
    """Distributed Matching-by-Clones Hungarian-Based Algorithm Orchestrator for warehouse task allocation."""

    def __init__(self, G, D, char_t, char_a, Lt=1, metric="RTP", task_ids=None, grid_map=None):
        self.G = G
        self.D = D
        self.char_t = char_t
        self.char_a = char_a
        self.Lt = Lt
        self.metric = metric
        self.task_ids = task_ids if task_ids is not None else list(range(len(char_t)))
        self.grid_map = grid_map

        self.na = G.shape[0]
        self.nt = len(char_t)

        self.start_time = time.perf_counter()

        # Initialize Agent
        self.agent_pos = []
        self.agent_speed = []
        self.agent_pos_grid = []
        for i in range(self.na):
            pos = np.array(self.char_a[i][:3])
            speed = self.char_a[i][3]
            self.agent_pos.append(pos)
            self.agent_speed.append(speed)
            if self.grid_map is not None:
                self.agent_pos_grid.append(self.grid_map.continuous_to_grid(*pos))
            else:
                self.agent_pos_grid.append(None)
        
        # Tracking 
        self.assig_history = []
        self.bid_history = []
        self.max_times = []

    def launch_agents(self, method=None, detector=None):
        """
        Run DMCHBA for task allocation.
        Returns:
            assignments: List of lists, where each sublist contains the task IDs assigned to the corresponding agent.
            total_score: Total score of the assignment (negative total cost).
            makespan: Time taken to compute the assignment.
        """
        G_nx = nx.from_numpy_array(self.G)
        components = list(nx.connected_components(G_nx))

        agent_paths = [[] for _ in range(self.na)]

        if (len(components) == 1):
            # Fully connected case: all agents see all tasks
            agent_indices = list(range(self.na))
            task_indices = list(range(self.nt))
            self._run_dmchba(agent_indices, task_indices, agent_paths)
        else:
            # Disconnected case: each component runs DMCHBA on its visible agents and tasks
            # Each component gets all remaining (unassigned) tasks — generous to baseline
            remaining_tasks_indices = set(range(self.nt))
            for comp in components:
                agent_indices = sorted(list(comp))
                task_indices = list(remaining_tasks_indices)  # All remaining tasks are visible to this component
                assigned_in_component = self._run_dmchba(agent_indices, task_indices, agent_paths)
                remaining_tasks_indices -= assigned_in_component

        # Build assignments in required format: lisst of lists of task IDs per agent
        assignment = []
        for i in range(self.na):
            assignment.append(list(agent_paths[i]))

        total_score, makespan = self._compute_score(agent_paths)

        self.assig_history.append(assignment)
        self.max_times.append(np.round(total_score, 6))
        self.bid_history.append(makespan)

        return assignment, np.round(total_score, 6), makespan
    
    def _run_dmchba(self, agent_indices, task_indices, agent_paths):
        """
        Core DMCHBA logic for a given set of agents and tasks.
        Clone Agents
        Build Cost Matrix
        Hungarian Assignment
        TSP Ordering
        """

        return None  # Placeholder for assigned task indices in this component
    
    
    def _compute_score(self, agent_paths):
        """
        Compute total score anbd makespan for the current assignment.
        """        
