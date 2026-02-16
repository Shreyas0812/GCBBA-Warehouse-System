"""
SGA (Sequential Greedy Algorithm) Orchestrator for warehouse task allocation.

Centralized upper bound baseline that GCBBA provably converges to.
Uses the same RPT bidding metric and BFS distance lookups as GCBBA.

When the communication graph is disconnected, SGA runs independently
within each connected component (generous to baseline).

Interface matches GCBBA_Orchestrator for drop-in replacement.
"""