"""
run_single_experiment.py
========================
Single-run runners for the main thesis comparison experiments (GCBBA vs CBBA vs SGA).
Collects all RunMetrics fields.

See run_single_ri_sensitivity_experiment.py for the rerun_interval sensitivity runner.
"""

import os
import sys
import time

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from integration.orchestrator import IntegrationOrchestrator
from Metrics import RunMetrics