"""
Task class for warehouse GCBBA
"""

import numpy as np


class GCBBA_Task:
    """
    Task class, defined by an id, an induct position (x,y,z), and eject position (x,y,z)
    """
    def __init__(self, id, char_t, grid_map=None):
        self.id = id
        self.induct_pos = np.array([char_t[0], char_t[1], char_t[2]])
        self.eject_pos = np.array([char_t[3], char_t[4], char_t[5]])

        # Precompute grid positions for BFS lookup
        if grid_map is not None:
            self.induct_grid = grid_map.continuous_to_grid(*self.induct_pos)
            self.eject_grid = grid_map.continuous_to_grid(*self.eject_pos)
        else:
            self.induct_grid = None
            self.eject_grid = None