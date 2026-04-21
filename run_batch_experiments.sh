#!/usr/bin/env bash
# run_batch_experiments.sh — Batch-mode thesis experiments across all environments.
#
# Execution order:
#   Group 1 (small maps):  warehouse_small → crossdock → kiva  (ca_star, then rhcr)
#   Group 2 (large maps):  warehouse_large → kiva_large → shelf_aisle  (ca_star, then rhcr)
#   Group 2 only starts after Group 1 fully completes.
#
# Usage:
#   bash run_batch_experiments.sh                  # full thesis run
#   bash run_batch_experiments.sh --mode quick     # smoke test only
#   bash run_batch_experiments.sh --workers 8      # override worker count (default: all cores)

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

# ── Resolve project root ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Activate venv ────────────────────────────────────────────────────────────
if [[ -f ".venv/bin/activate" ]]; then
    source .venv/bin/activate
elif [[ -f ".venv/Scripts/activate" ]]; then
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
    local planner="$3"
    local label="$4"
    echo ""
    echo "============================================================"
    echo "  MAP: $map | config: $config | planner: $planner | mode: $MODE"
    echo "  $label"
    echo "============================================================"
    python experiments/run_experiments.py \
        --map        "$map" \
        --mode       "$MODE" \
        --config     "$config" \
        --workers    "$WORKERS" \
        --path-planner "$planner"
}

# ════════════════════════════════════════════════════════════════════════════
#  GROUP 1 — Small maps  (warehouse_small, crossdock, kiva)
# ════════════════════════════════════════════════════════════════════════════
echo ""
echo "████████████████████████████████████████████████████████████████████"
echo "  GROUP 1 — Small maps — ca_star"
echo "████████████████████████████████████████████████████████████████████"

run_exp gridworld_warehouse_small  batch_only  ca_star  "N=6  — GCBBA + CBBA + SGA + DMCHBA"
run_exp gridworld_crossdock        batch_only  ca_star  "N=50 — GCBBA + CBBA + SGA + DMCHBA"
run_exp gridworld_kiva             batch_only  ca_star  "N=100 — GCBBA + CBBA + SGA + DMCHBA"

echo ""
echo "████████████████████████████████████████████████████████████████████"
echo "  GROUP 1 — Small maps — rhcr"
echo "████████████████████████████████████████████████████████████████████"

run_exp gridworld_warehouse_small  batch_only  rhcr  "N=6  — GCBBA + CBBA + SGA + DMCHBA"
run_exp gridworld_crossdock        batch_only  rhcr  "N=50 — GCBBA + CBBA + SGA + DMCHBA"
run_exp gridworld_kiva             batch_only  rhcr  "N=100 — GCBBA + CBBA + SGA + DMCHBA"

echo ""
echo "============================================================"
echo "  GROUP 1 complete."
echo "============================================================"

# ════════════════════════════════════════════════════════════════════════════
#  GROUP 2 — Large maps  (warehouse_large, kiva_large, shelf_aisle)
# ════════════════════════════════════════════════════════════════════════════
echo ""
echo "████████████████████████████████████████████████████████████████████"
echo "  GROUP 2 — Large maps — ca_star"
echo "████████████████████████████████████████████████████████████████████"

run_exp gridworld_warehouse_large  batch_only  ca_star  "N=18  — GCBBA + CBBA + SGA + DMCHBA"
run_exp gridworld_kiva_large       batch_only  ca_star  "N=200 — GCBBA + DMCHBA"
run_exp gridworld_shelf_aisle      batch_only  ca_star  "N=470 — GCBBA + DMCHBA"

echo ""
echo "████████████████████████████████████████████████████████████████████"
echo "  GROUP 2 — Large maps — rhcr"
echo "████████████████████████████████████████████████████████████████████"

run_exp gridworld_warehouse_large  batch_only  rhcr  "N=18  — GCBBA + CBBA + SGA + DMCHBA"
run_exp gridworld_kiva_large       batch_only  rhcr  "N=200 — GCBBA + DMCHBA"
run_exp gridworld_shelf_aisle      batch_only  rhcr  "N=470 — GCBBA + DMCHBA"

echo ""
echo "============================================================"
echo "  GROUP 2 complete."
echo "  All batch experiments done."
echo "  Results written to results/experiments/<map>/<timestamp>/"
echo "============================================================"
