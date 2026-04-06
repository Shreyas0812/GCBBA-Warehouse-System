"""
Calculates the BFS distances and returns the average service time (in timesteps) for a task in the given map. This is used to set the capacity parameter for the LCBA sensitivity experiments.

Average service time = mean(induct → eject) + mean(eject → induct)
This models the full agent cycle: reposition from last eject to next induct, then deliver to eject.
"""

import argparse
from collections import deque
import numpy as np
import yaml


def load_map(map_path: str) -> dict:
    """Loads a map from a YAML file."""
    with open(map_path, 'r') as f:
        map_data = yaml.safe_load(f)
    return map_data

def compute_bfs_distances(map_data: dict) -> dict:
    """
    Builds a 2D occupancy grid from map_data and runs BFS from every induct
    and every eject station.

    Returns:
        {
            "induct_bfs": {(x, y): {(x, y): dist, ...}, ...},
            "eject_bfs":  {(x, y): {(x, y): dist, ...}, ...},
            "induct_positions": [(x, y), ...],
            "eject_positions":  [(x, y), ...],
        }
    """
    params = map_data["create_gridworld_node"]["ros__parameters"]
    width  = params["grid_width"]
    height = params["grid_height"]

    # 0=free, 1=obstacle, 2=induct, 3=eject
    grid = np.zeros((height, width), dtype=np.int8)

    # Mark obstacles from flattened [x1,y1,z1, x2,y2,z2, ...] regions
    obs = params.get("obstacle_regions", [])
    for i in range(0, len(obs), 6):
        x1, y1, _, x2, y2, _ = obs[i], obs[i+1], obs[i+2], obs[i+3], obs[i+4], obs[i+5]
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                if 0 <= x < width and 0 <= y < height:
                    grid[y, x] = 1

    # Parse station list from flattened [x, y, z, id, ...] and mark on grid
    def parse_stations(flat, cell_type):
        positions = []
        for i in range(0, len(flat), 4):
            x, y = flat[i], flat[i + 1]
            grid[y, x] = cell_type
            positions.append((x, y))
        return positions

    induct_positions = parse_stations(params.get("induct_stations", []), 2)
    eject_positions  = parse_stations(params.get("eject_stations",  []), 3)

    def get_neighbors(x, y):
        cell_type = grid[y, x]
        neighbors = []
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if grid[ny, nx] == 1:
                continue
            neighbor_type = grid[ny, nx]
            # Preserve GridMap constraint: no induct→induct or eject→eject traversal
            if cell_type == 2 and neighbor_type == 2:
                continue
            if cell_type == 3 and neighbor_type == 3:
                continue
            neighbors.append((nx, ny))
        return neighbors

    def bfs_from(sx, sy):
        dist = {(sx, sy): 0}
        queue = deque([(sx, sy)])
        while queue:
            x, y = queue.popleft()
            for nx, ny in get_neighbors(x, y):
                if (nx, ny) not in dist:
                    dist[(nx, ny)] = dist[(x, y)] + 1
                    queue.append((nx, ny))
        return dist

    induct_bfs = {pos: bfs_from(*pos) for pos in induct_positions}
    eject_bfs  = {pos: bfs_from(*pos) for pos in eject_positions}

    return {
        "induct_bfs":       induct_bfs,
        "eject_bfs":        eject_bfs,
        "induct_positions": induct_positions,
        "eject_positions":  eject_positions,
    }

def calculate_average_service_time(map_path: str) -> float:
    """
    Loads map_path, runs BFS, and returns:
        mean(induct → eject) + mean(eject → induct)
    Unreachable pairs are excluded from the average.
    """
    map_data = load_map(map_path)
    bfs = compute_bfs_distances(map_data)

    induct_to_eject = [
        bfs["induct_bfs"][i][e]
        for i in bfs["induct_positions"]
        for e in bfs["eject_positions"]
        if e in bfs["induct_bfs"][i]
    ]
    eject_to_induct = [
        bfs["eject_bfs"][e][i]
        for e in bfs["eject_positions"]
        for i in bfs["induct_positions"]
        if i in bfs["eject_bfs"][e]
    ]

    if not induct_to_eject or not eject_to_induct:
        return float('inf')

    return sum(induct_to_eject) / len(induct_to_eject) + sum(eject_to_induct) / len(eject_to_induct)

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Calculate average service time for a map")
    parser.add_argument("--map", help="Path to the map YAML file", default="../../config/gridworld_warehouse_small.yaml")
    args = parser.parse_args()

    avg_service_time = calculate_average_service_time(args.map)
    print(f"Average service time (timesteps) for a task in map {args.map}: {avg_service_time:.2f}")