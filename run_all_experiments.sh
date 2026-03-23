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
#   warehouse_small  — all         (N=6,   ss + batch, all methods)
#   warehouse_large  — all         (N=18,  ss + batch, all methods)
#   crossdock        — gcbba_dmchba (N=50,  GCBBA + DMCHBA ss+batch; CBBA/SGA batch too slow)
#   kiva             — gcbba_dmchba (N=100, same reasoning)
#   kiva_large       — gcbba_dmchba (N=200, GCBBA + DMCHBA ss+batch; CBBA/SGA removed)
#   shelf_aisle      — gcbba_dmchba (N=470, same reasoning)

set -euo pipefail

# ── Defaults ────────────────────────────────────────────────────────────────
MODE="full"
WORKERS=0   # 0 = auto-detect all cores

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
        --workers "$WORKERS"
}

# ── Smoke test (always quick, warehouse_small) ───────────────────────────────
echo ""
echo "=== Smoke test (quick, warehouse_small, all) ==="
python experiments/run_experiments.py \
    --map gridworld_warehouse_small \
    --mode quick \
    --config all \
    --workers 1
echo "Smoke test passed."

# ── Skip the full run if mode is quick ──────────────────────────────────────
if [[ "$MODE" == "quick" ]]; then
    echo ""
    echo "mode=quick: smoke test only, exiting."
    exit 0
fi

# ── warehouse_small — GCBBA + baselines, ss + batch ─────────────────────────
run_exp gridworld_warehouse_small all "GCBBA + baselines (ss + batch)"

# ── warehouse_large — GCBBA + baselines, ss + batch ─────────────────────────
run_exp gridworld_warehouse_large all "GCBBA + baselines (ss + batch)"

# ── crossdock — GCBBA + DMCHBA ss+batch; skip CBBA/SGA batch ────────────────
run_exp gridworld_crossdock gcbba_dmchba "GCBBA + DMCHBA ss+batch (N=50)"

# ── kiva — GCBBA + DMCHBA ss+batch; skip CBBA/SGA batch ─────────────────────
run_exp gridworld_kiva gcbba_dmchba "GCBBA + DMCHBA ss+batch (N=100)"

# ── kiva_large — GCBBA + DMCHBA only; no CBBA/SGA ───────────────────────────
run_exp gridworld_kiva_large gcbba_dmchba "GCBBA + DMCHBA ss+batch (N=200)"

# ── shelf_aisle — GCBBA + DMCHBA only; no CBBA/SGA ──────────────────────────
run_exp gridworld_shelf_aisle gcbba_dmchba "GCBBA + DMCHBA ss+batch (N=470)"

echo ""
echo "============================================================"
echo "  All environments complete."
echo "  Results written to results/experiments/<map>/<timestamp>/"
echo "============================================================"
