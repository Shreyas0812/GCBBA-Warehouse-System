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