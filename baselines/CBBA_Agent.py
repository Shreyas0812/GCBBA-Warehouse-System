"""
CBBA Agent class for Warehouse Task Allocation.

Standard CBBA (Choi et al. 2009) baseline:
- FULLBUNDLE bundle building: fills entire bundle in a while loop before consensus
- Same consensus/conflict resolution as GCBBA
- No convergence detection
"""

import numpy as np

from gcbba.GCBBA_Agent import GCBBA_Agent

class CBBA_Agent(GCBBA_Agent):
    """
    Same functoins as GCBBA_Agent but overrides create_bundle() to use FULLBUNDLE strategy.
        - GCBBA (ADD): adds ONE task per create_bundle() call, then 2D consensus rounds
        - CBBA (FULLBUNDLE): adds ALL tasks up to capacity in one create_bundle() call, 
        then 1 consensus round

    Similarly in resolve_conflicts(), CBBA only does 1 round of conflict resolution after bundle building, no convergence detection.
    
    Other functionality remaints the same
    """

    def __init__(self, id, G, char_a, tasks, Lt=2, start_time=0, metric="RPT", D=1, grid_map=None):
        super().__init__(id, G, char_a, tasks, Lt, start_time, metric, D, grid_map)
        # CBBA does not use convergence detection
        self.converged = False

    def create_bundle(self):
        """
        FULLBUNDLE strategy: greedily add tasks to bundle until capacity is reached
        or no more tasks can improve the path.
        
        This fills the entire bundle in one call (standard CBBA Phase 1).
        """
        while len(self.p) < self.Lt:
            # Recompute all bids from scratch each time a task is added
            optimal_placement = np.zeros(self.nt)
            filtered_task_ids = [t.id for t in self.tasks if t.id not in self.p]

            if not filtered_task_ids:
                return

            for task_id in filtered_task_ids:
                task_idx = self._get_task_index(task_id)
                c, opt_place = self.compute_c(task_id)
                self.c[task_idx] = c
                optimal_placement[task_idx] = opt_place

            # Select best task that beats current winning bid
            bids = []
            for j in range(self.nt):
                task_id = self.tasks[j].id
                if task_id not in filtered_task_ids:
                    bids.append(self.min_val)
                    continue

                if self.c[j] > self.y[j]:
                    bids.append(self.c[j])
                elif self.c[j] == self.y[j] and self.z[j] is not None and self.id < self.z[j]:
                    bids.append(self.c[j])
                else:
                    bids.append(self.min_val)

            best_bid_idx = np.argmax(bids)
            best_task_id = self.tasks[best_bid_idx].id

            if best_task_id in self.p or bids[best_bid_idx] <= self.min_val:
                break  # No valid task to add, exit loop
            
            # Add best task to bundle and path
            self.b.append(best_task_id)
            self.p.insert(optimal_placement[best_bid_idx], best_task_id)
            self.S.append(self.evaluate_path(self.p))

            self.y[best_bid_idx] = self.c[best_bid_idx]
            self.z[best_bid_idx] = self.id
    