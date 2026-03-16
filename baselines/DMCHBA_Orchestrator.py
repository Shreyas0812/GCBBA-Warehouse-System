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

        # Initialize Tasks
        self.tasks = []
        for j in range(self.nt):
            self.tasks.append(GCBBA_Task(id=self.task_ids[j], char_t=self.char_t[j], grid_map=self.grid_map))

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
        Map clone assignments back to real agents and tasks
        TSP Ordering
        """

        n_agents = len(agent_indices)
        n_tasks = len(task_indices)

        if n_agents == 0 or n_tasks == 0:
            return set()  # No assignments possible

        # Step 1: Determine number of clones per agent
        clones_per_agent = ceil(n_tasks / n_agents)
        total_clones = clones_per_agent * n_agents

        # Step 2: Build cost matrix (total_clones x n_tasks)
        # Rows: clones, Columns: tasks
        cost_matrix = np.full((total_clones, n_tasks), fill_value=1e9)  # Large cost for unassignable pairs

        for a_local, a_global in enumerate(agent_indices):
            for clone_idx in range(clones_per_agent):
                clone_row = a_local * clones_per_agent + clone_idx
                for t_local, t_global in enumerate(task_indices):
                    task = self.tasks[t_global]

                    # Cost: agent -> induct -> eject 
                    dist_to_induct = self._get_distance(self.agent_pos[a_global], self.agent_pos_grid[a_global], task.induct_pos, task.induct_grid)
                    dist_induct_to_eject = self._get_distance(task.induct_pos, task.induct_grid, task.eject_pos, task.eject_grid)

                    speed = self.agent_speed[a_global]
                    cost_matrix[clone_row, t_local] = (dist_to_induct + dist_induct_to_eject) / speed

        if total_clones > n_tasks:
            # Pad cost matrix to be square by adding dummy tasks with high cost
            padding = np.full((total_clones, total_clones - n_tasks), fill_value=1e9)  # Large cost for dummy tasks
            cost_matrix = np.hstack((cost_matrix, padding))

        # Step 3: Hungarian Assignment
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        # Step 4: Map clone assignments back to real agents and tasks
        agent_task_map = {a_local: [] for a_local in range(n_agents)}
        assigned_task_indices = set()

        for row, col in zip(row_ind, col_ind):
            if col < n_tasks: # Ignore dummy task assignments
                a_local = row // clones_per_agent
                t_global = task_indices[col]
                agent_task_map[a_local].append(col)  # Map back to global task index
                assigned_task_indices.add(col)

        # Step 5: TSP Ordering (2-opt) for each agent's assigned tasks
        for a_local, a_global in enumerate(agent_indices):
            local_task_cols = agent_task_map[a_local]
            if len(local_task_cols) == 0:
                continue  # No tasks assigned to this agent

            global_task_indices = [task_indices[t_col] for t_col in local_task_cols]

            if len(global_task_indices) == 0:
                agent_paths[a_global] = self.tasks[global_task_indices][0].id  # Single task, no ordering needed
            else:
                # 2-opt TSP ordering
                best_order = self._two_opt_tsp(a_global, global_task_indices)
                agent_paths[a_global] = [self.tasks[t_idx].id for t_idx in best_order]

        return {task_indices[t_col] for t_col in assigned_task_indices}

    # tsp 2-opt heuristic for ordering tasks assigned to an agent
    def _two_opt_tsp(self, agent_idx, task_global_indices):
        """
        2-opt TSP to order tasks for a single agent.
        """    
        n = len(task_global_indices)
        if n <= 2:
            return task_global_indices  # No ordering needed for 2 or fewer tasks
        
        # Initial order (as assigned by Hungarian)
        route = list(task_global_indices)

        best_cost = self.total_tour_cost(route, agent_idx)
        improved = True

        while improved:
            improved = False
            for i in range(1, n - 1):
                for j in range(i + 1, n):
                    new_route = route[:i] + route[i:j+1][::-1] + route[j+1:]
                    new_cost = self.total_tour_cost(new_route, agent_idx)
                    if new_cost < best_cost - 1e-9:  # Consider a small threshold for improvement
                        route = new_route
                        best_cost = new_cost
                        improved = True
        
        return route

    # Helper functions to compute distances and costs
    def route_cost(self, from_pos, from_grid, to_task_idx, agent_idx):
        """
        Cost to travel to task and execute it (induct + eject).
        """
        task = self.tasks[to_task_idx]
        dist_to_induct = self._get_distance(from_pos, from_grid, task.induct_pos, task.induct_grid)
        dist_induct_to_eject = self._get_distance(task.induct_pos, task.induct_grid, task.eject_pos, task.eject_grid)
        return (dist_to_induct + dist_induct_to_eject) / self.agent_speed[agent_idx]
    
    def leg_cost(self, from_task_idx, to_task_idx, agent_idx):
        """
        Cost to travel between two tasks (eject of first to induct of second).
        """
        task_from = self.tasks[from_task_idx]
        
        return self.route_cost(task_from.eject_pos, task_from.eject_grid, to_task_idx, agent_idx)
    
    def total_tour_cost(self, route, agent_idx):
        """
        Total cost of a given route (sequence of task indices) for an agent.
        """
        cost = self.route_cost(self.agent_pos[agent_idx], self.agent_pos_grid[agent_idx], route[0], agent_idx)  # Start to first task
        for k in range(1, len(route)):
            cost += self.leg_cost(route[k-1], route[k], agent_idx)  # Between tasks
        return cost
    
    def _get_distance(self, pos, pos_grid, target_pos, target_grid):
        """
        Get distance between two positions, using BFS if grid info is available.
        """
        if self.grid_map is None or pos_grid is None or target_grid is None:
            return np.linalg.norm(np.array(pos) - np.array(target_pos))
        
        # BFS from target (targer is station)
        table = self.grid_map.bfs_distances_from_station.get(target_grid)
        if table is not None and pos_grid in table:
            return table[pos_grid]
        
        # BFS from pos (pos is station)
        table = self.grid_map.bfs_distances_from_station.get(pos_grid)
        if table is not None and target_grid in table:
            return table[target_grid]
        
        # Fallback to Euclidean if BFS info is missing
        return np.linalg.norm(np.array(pos) - np.array(target_pos))


    def _compute_score(self, agent_paths):
        """
        Compute total score anbd makespan for the current assignment.
        """        
        total_score = 0
        makespan = 0

        for i in range(self.na):
            if not agent_paths[i]:  # No tasks assigned to this agent
                continue

            path_score = self._evaluate_path(i, agent_paths[i])
            completion_time = -path_score  # Since score is negative cost

            total_score += path_score

            if completion_time > makespan:
                makespan = completion_time
        
        return total_score, makespan
    
    def _evaluate_path(self, agent_idx, path):
        """
        Evaluate RPT score for a given agent's path (sequence of task IDs).
        """
        cur_pos = self.agent_pos[agent_idx]
        cur_grid = self.agent_pos_grid[agent_idx]
        speed = self.agent_speed[agent_idx]
        score = 0
        time_elapsed = 0

        for task_id in path:
            task = self._get_task_by_id(task_id)

            # Travel to induct
            time_elapsed += self._get_distance(cur_pos, cur_grid, task.induct_pos, task.induct_grid) / speed

            # Execute task (induct + eject)
            time_elapsed += self._get_distance(task.induct_pos, task.induct_grid, task.eject_pos, task.eject_grid) / speed

            score -= time_elapsed  # RPT: negative completion time

            time_elapsed = 0  # Reset time for next task since RPT only cares about completion time of each task

            # Update position for next leg
            cur_pos = task.eject_pos
            cur_grid = task.eject_grid

        return score
    
    def _get_task_by_id(self, task_id):
        """
        Helper to get task object by its ID.
        """
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None  # Should not happen if IDs are consistent
