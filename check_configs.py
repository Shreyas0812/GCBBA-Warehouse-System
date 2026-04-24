import yaml, sys
sys.stdout.reconfigure(encoding='utf-8')

maps = [
    'gridworld_warehouse_small',
    'gridworld_warehouse_large',
    'gridworld_kiva',
    'gridworld_kiva_large',
    'gridworld_crossdock',
    'gridworld_shelf_aisle',
]

def parse_positions(flat, stride=4):
    return {(flat[i], flat[i+1], flat[i+2]) for i in range(0, len(flat), stride)}

def expand_obstacles(regions):
    obs = set()
    for i in range(0, len(regions), 6):
        x0,y0,z0,x1,y1,z1 = regions[i:i+6]
        for x in range(x0, x1+1):
            for y in range(y0, y1+1):
                for z in range(z0, z1+1):
                    obs.add((x,y,z))
    return obs

def free_neighbors(pos, obstacles, grid_w, grid_h):
    x, y, z = pos
    return [(x+dx,y+dy,z) for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]
            if 0 <= x+dx < grid_w and 0 <= y+dy < grid_h
            and (x+dx,y+dy,z) not in obstacles]

for m in maps:
    path = f'config/{m}.yaml'
    with open(path) as f:
        cfg = yaml.safe_load(f)
    p = cfg['create_gridworld_node']['ros__parameters']
    grid_w = p.get('grid_width', 30)
    grid_h = p.get('grid_height', 30)

    obstacles  = expand_obstacles(p.get('obstacle_regions', []))
    inductpos  = parse_positions(p['induct_stations'])
    ejectpos   = parse_positions(p['eject_stations'])
    chargepos  = parse_positions(p['charging_stations'])
    waitpos    = parse_positions(p['idle_task_stations'])
    agentpos   = parse_positions(p['agent_positions'])
    all_occupied = obstacles | inductpos | ejectpos | chargepos

    print(f"\n{'='*60}")
    print(f"MAP: {m}  ({grid_w}x{grid_h})")
    print(f"{'='*60}")

    # Overlap checks for idle_task stations
    issues = False
    for other_label, other in [('obstacle',obstacles),('induct',inductpos),('eject',ejectpos),('charger',chargepos),('agent_start',agentpos)]:
        overlap = waitpos & other
        if overlap:
            print(f"  [OVERLAP] idle_task intersects {other_label}: {sorted(overlap)}")
            issues = True
    if not issues:
        print("  Overlaps: none")

    # Idle-task accessibility
    print("  Idle-task stations:")
    for pos in sorted(waitpos):
        free = free_neighbors(pos, obstacles, grid_w, grid_h)
        tag = "BOTTLENECK(1 way in/out)" if len(free)==1 else "ISOLATED" if len(free)==0 else "OK"
        print(f"    {pos}: {len(free)} free neighbors -- {tag}")

    # Induct accessibility
    print("  Induct stations:")
    for pos in sorted(inductpos):
        free = free_neighbors(pos, all_occupied - inductpos, grid_w, grid_h)
        tag = "SINGLE ACCESS" if len(free)==1 else "ISOLATED" if len(free)==0 else "OK"
        print(f"    {pos}: {len(free)} free neighbors -- {tag}")

    # Eject bottlenecks
    bad_ejects = []
    for pos in sorted(ejectpos):
        free = free_neighbors(pos, all_occupied - ejectpos, grid_w, grid_h)
        if len(free) <= 1:
            bad_ejects.append((pos, len(free)))
    if bad_ejects:
        print(f"  Eject bottlenecks ({len(bad_ejects)}/{len(ejectpos)}):")
        for pos,n in bad_ejects:
            print(f"    {pos}: {n} free neighbor -- BOTTLENECK")
    else:
        print(f"  Eject stations: all >=2 free neighbors -- OK")
