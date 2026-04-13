#!/usr/bin/env bash
# run_ri_sensitivity_experiments.sh
# Runs the rerun_interval sensitivity sweep for all available maps sequentially.
# Usage: bash run_ri_sensitivity_experiments.sh [--workers N]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKERS=${1:-0}  # pass --workers N as first arg, or leave 0 for auto

MAPS=(
    gridworld_warehouse_small
    gridworld_warehouse_large
    gridworld_crossdock
    gridworld_kiva
    gridworld_kiva_large
    gridworld_shelf_aisle
)

echo "======================================================"
echo "RI Sensitivity Sweep — all maps"
echo "Workers: ${WORKERS} (0 = auto)"
echo "======================================================"

for MAP in "${MAPS[@]}"; do
    echo ""
    echo ">>> Starting: ${MAP}"
    python "${SCRIPT_DIR}/experiments/run_lcba_sensitivity_experiments.py" \
        --map "${MAP}" \
        --workers "${WORKERS}"
    echo "<<< Done: ${MAP}"

    # Find the most recent summary.csv for this map and plot it
    RESULTS_DIR="${SCRIPT_DIR}/results/experiments/${MAP}/rerun_interval_sensitivity"
    LATEST_CSV=$(find "${RESULTS_DIR}" -name "summary.csv" -printf "%T@ %p\n" 2>/dev/null | sort -n | tail -1 | awk '{print $2}')
    if [ -n "${LATEST_CSV}" ]; then
        echo ">>> Plotting: ${LATEST_CSV}"
        python "${SCRIPT_DIR}/experiments/plotting/plot_ri_sensitivity.py" \
            --csv "${LATEST_CSV}" \
            --save
        echo "<<< Plot saved alongside summary.csv"
    else
        echo "WARNING: No summary.csv found for ${MAP}, skipping plot."
    fi
done

echo ""
echo "======================================================"
echo "All maps complete."
echo "======================================================"
