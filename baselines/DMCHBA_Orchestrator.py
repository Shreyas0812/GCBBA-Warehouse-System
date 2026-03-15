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

