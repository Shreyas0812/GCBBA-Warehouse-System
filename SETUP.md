# Setup Guide — New Machine

Steps to get the project running after cloning on a fresh system (Linux assumed for college machine).

---

## 1. Prerequisites

- Python 3.10 or later
- git

Check versions:
```bash
python3 --version
git --version
```

---

## 2. Clone the repo

```bash
git clone <your-repo-url>
cd GCBBA_Warehouse_System
```

---

## 3. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should now show `(.venv)`. All subsequent commands assume the venv is active.

---

## 4. Install the package and dependencies

```bash
# Install the project itself (editable mode so imports resolve correctly)
pip install -e .

# Additional packages used by the experiment runner and plotting
pip install scipy pandas tqdm psutil
```

Full list of what ends up installed:
| Package | Used for |
|---------|----------|
| numpy | simulation numerics |
| pyyaml | config file parsing |
| matplotlib | plotting |
| networkx | communication graph |
| scipy | stats in analysis |
| pandas | results aggregation |
| tqdm | progress bars |
| psutil | machine info in experiment_config.json |

---

## 5. Verify the install

```bash
# Should print without errors
python -c "from integration.orchestrator import IntegrationOrchestrator; print('OK')"
```

---

## 6. Check available CPU cores

Before running parallel experiments, check the machine's core count to avoid oversubscription:

```bash
nproc                              # logical cores available to this process
nproc --all                        # total logical cores
lscpu | grep "Core(s) per socket"  # physical cores per socket
lscpu | grep "Socket(s)"           # number of sockets
```

Use **physical cores** (not logical/hyperthreaded) as your `--workers` value, since each simulation step is pure compute.

---

## 7. Run a quick smoke test first

Always do a quick run before committing to a long experiment to confirm everything works:

```bash
python experiments/run_experiments.py \
  --map gridworld_warehouse_small \
  --mode quick \
  --config ss_only \
  --workers 1
```

Expected output: a few runs printing `tput=...` lines, then a summary CSV written to `results/experiments/gridworld_warehouse_small/<timestamp>/`.

---

## 8. Run the main experiments

### warehouse_small (baseline, re-run with new analytical configs)
```bash
python experiments/run_experiments.py \
  --map gridworld_warehouse_small \
  --mode medium \
  --config ss_only \
  --workers <N>
```

### warehouse_large (scaling experiment)
```bash
python experiments/run_experiments.py \
  --map gridworld_warehouse_large \
  --mode medium \
  --config ss_only \
  --workers <N>
```

Since this is a dedicated machine, use `--workers 0` to auto-detect and use all cores.

---

## 9. Results

Results are written to:
```
results/experiments/<map_name>/<timestamp>/
    experiment_config.json   ← run parameters + machine info
    summary.csv              ← one row per run
    summary_with_optimality.csv
    <run_id>/
        metrics.json
        trajectories.csv
```

---

## 10. Notes on wall-clock limits and parallelism

- The experiment runner caps each run at **600s wall-clock time** (`WALL_CLOCK_LIMIT_S`).
- This is measured in real elapsed time inside each worker process.
- On a dedicated machine, `--workers 0` (all cores) is safe and gives maximum parallelism. On a shared machine, keep `--workers ≤ physical_core_count` to avoid oversubscription inflating wall time.
- CBBA and SGA runs at high arrival rates are the slowest — they will most often hit the 600s cap on large maps.

---

## 11. Keeping the venv active across sessions

The venv deactivates when the shell session ends. Re-activate it each time:

```bash
source .venv/bin/activate
```

Or add it to your shell rc file if you want it automatic:
```bash
echo "source ~/GCBBA_Warehouse_System/.venv/bin/activate" >> ~/.bashrc
```

---

## Appendix: Baseline strategy for large maps

For very large maps (kiva, kiva_large, shelf_aisle), running CBBA and SGA alongside GCBBA is not practical and not necessary. This is a feature, not a gap.

### Why skip CBBA/SGA on large maps

On maps with 100–470 agents, CBBA and SGA hit the per-call allocation timeout (`allocation_timeout_s=10s`) repeatedly and can barely complete any simulation steps. Their throughput approaches zero — not because they perform poorly on the task, but because they cannot compute an allocation fast enough to keep up with the simulation. This is a fundamentally different failure mode from "lower throughput" and would muddy any direct comparison.

### Recommended per-map strategy

| Map | Agents | GCBBA | CBBA/SGA |
|-----|--------|-------|----------|
| warehouse_small | 6 | Full sweep | Full sweep |
| warehouse_large | 18 | Full sweep | Full sweep |
| crossdock | 50 | Full sweep | Worth trying |
| kiva | 100 | Full sweep | 1 seed only (to record intractability) |
| kiva_large | 200 | Full sweep | Skip |
| shelf_aisle | 470 | Full sweep | Skip |

### The intractability run (kiva only)

Run one seed of CBBA/SGA on kiva at a single arrival rate and comm range:

```bash
python experiments/run_experiments.py \
  --map gridworld_kiva \
  --mode quick \
  --config baselines_only \
  --workers 0
```

This gives you concrete data (`hit_wall_clock_ceiling=True`, `num_allocation_timeouts > 0`) to cite in the thesis as evidence of intractability at scale, rather than just asserting it.

### How to run GCBBA-only on large maps

Use `--config gcbba_only` — wait, the current filter options don't include that directly. Use `--config dynamic_only` to get the canonical dynamic GCBBA, or `--config static_only` for static. To get all GCBBA variants (static + dynamic + sensitivity sweep) without baselines, run:

```bash
# All GCBBA variants, no CBBA/SGA
python experiments/run_experiments.py \
  --map gridworld_kiva \
  --mode medium \
  --config ss_only \
  --workers 0
```

Then filter out CBBA/SGA from the results in post-processing using `config_name` column in `summary.csv`, or add `--skip-baselines` flag if implemented.

### Thesis framing

> "GCBBA scales to N=470 agents with stable throughput. CBBA and SGA are computationally intractable at this scale, consistently exceeding the per-call allocation timeout of 10s on kiva (N=100), preventing meaningful simulation progress."

This is a stronger claim than "GCBBA has higher throughput" — it demonstrates a qualitative scaling advantage.
