#!/usr/bin/env bash
# run_all_experiments.sh — Run thesis experiments across all environments sequentially.
#
# Usage:
#   bash run_all_experiments.sh                  # full thesis run
#   bash run_all_experiments.sh --mode medium    # faster / initial results
#   bash run_all_experiments.sh --mode quick     # smoke test only
#   bash run_all_experiments.sh --workers 8      # override worker count
#
# Per-map strategy (from SETUP.md):
#   warehouse_small  — all         (N=6,   ss + batch, GCBBA + CBBA + SGA + DMCHBA)
#   warehouse_large  — all         (N=18,  ss + batch, GCBBA + CBBA + SGA + DMCHBA)
#   crossdock        — gcbba_dmchba (N=12,  GCBBA + DMCHBA ss+batch; CBBA/SGA batch too slow)
#   kiva             — gcbba_dmchba (N=20,  same reasoning)
#   kiva_large       — gcbba_dmchba (N=80,  GCBBA + DMCHBA ss+batch; CBBA/SGA removed)
#   shelf_aisle      — gcbba_dmchba (N=200, same reasoning)

set -euo pipefail

# ── Defaults ────────────────────────────────────────────────────────────────
MODE="full"
WORKERS=12

# ── Parse arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)    MODE="$2";    shift 2 ;;
        --workers) WORKERS="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ── Resolve project root (directory containing this script) ─────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Activate venv ────────────────────────────────────────────────────────────
if [[ -f ".venv/bin/activate" ]]; then
    source .venv/bin/activate
elif [[ -f ".venv/Scripts/activate" ]]; then
    # Windows Git Bash / MSYS2
    source .venv/Scripts/activate
else
    echo "ERROR: .venv not found. Run setup first (see SETUP.md)."
    exit 1
fi

# ── Verify install ───────────────────────────────────────────────────────────
echo "=== Verifying install ==="
python -c "from integration.orchestrator import IntegrationOrchestrator; print('OK')"

# ── Helper ───────────────────────────────────────────────────────────────────
run_exp() {
    local map="$1"
    local config="$2"
    local label="$3"
    echo ""
    echo "============================================================"
    echo "  MAP: $map | config: $config | mode: $MODE | $label"
    echo "============================================================"
    python experiments/run_experiments.py \
        --map "$map" \
        --mode "$MODE" \
        --config "$config" \
        --workers "$WORKERS" \
        --path-planner rhcr
}


run_exp gridworld_warehouse_small all "GCBBA + CBBA + SGA + DMCHBA (ss + batch) N=6"
run_exp gridworld_warehouse_large all "GCBBA + CBBA + SGA + DMCHBA (ss + batch) N=18"
run_exp gridworld_crossdock        all "GCBBA + CBBA + SGA + DMCHBA (ss + batch) N=12"
run_exp gridworld_kiva             all "GCBBA + CBBA + SGA + DMCHBA (ss + batch) N=20"
run_exp gridworld_kiva_large       all "GCBBA + CBBA + SGA + DMCHBA (ss + batch) N=80"
run_exp gridworld_shelf_aisle      all "GCBBA + CBBA + SGA + DMCHBA (ss + batch) N=200"


echo ""
echo "============================================================"
echo "  All environments complete."
echo "  Results written to results/experiments/<map>/<timestamp>/"
echo "============================================================"
