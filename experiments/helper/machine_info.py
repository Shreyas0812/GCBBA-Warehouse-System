import platform
import subprocess
import os
import json

from typing import Dict

def collect_machine_info() -> Dict:
    """
    Collect hardware and software environment info for reproducibility.
    All fields are best-effort — failures are caught and noted rather than raised.
    """

    info: Dict = {}

    # ── Python / OS ───────────────────────────────────────────────
    info["python_version"] = platform.python_version()
    info["platform"] = platform.platform()
    info["hostname"] = platform.node()

    # ── CPU ───────────────────────────────────────────────────────
    info["cpu_logical_cores"] = os.cpu_count()
    try:
        import psutil
        info["cpu_physical_cores"] = psutil.cpu_count(logical=False)
        info["ram_total_gb"] = round(psutil.virtual_memory().total / 1024**3, 2)
        info["ram_available_gb"] = round(psutil.virtual_memory().available / 1024**3, 2)
    except ImportError:
        info["cpu_physical_cores"] = "psutil not installed"
        info["ram_total_gb"] = "psutil not installed"

    try:
        info["cpu_model"] = platform.processor() or "unknown"
    except Exception:
        info["cpu_model"] = "unknown"

    # ── GPU (nvidia-smi) ─────────────────────────────────────────
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            gpus = []
            for line in result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) == 3:
                    gpus.append({
                        "name": parts[0],
                        "vram_mb": parts[1],
                        "driver": parts[2],
                    })
            info["gpus"] = gpus
        else:
            info["gpus"] = "nvidia-smi returned non-zero"
    except FileNotFoundError:
        info["gpus"] = "nvidia-smi not found"
    except Exception as e:
        info["gpus"] = f"error: {e}"

    # ── Key package versions ──────────────────────────────────────
    versions: Dict = {}
    for pkg in ("numpy", "scipy", "networkx", "psutil"):
        try:
            import importlib.metadata
            versions[pkg] = importlib.metadata.version(pkg)
        except Exception:
            versions[pkg] = "unknown"
    info["package_versions"] = versions

    return info

if __name__ == "__main__":
    machine_info = collect_machine_info()
    print(json.dumps(machine_info, indent=2))