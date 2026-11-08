import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "src" / "jobs"
sys.path.insert(0, str(JOBS))
sys.path.insert(0, str(ROOT / "src" / "analysis"))
sys.path.insert(0, str(ROOT / "src" / "datagen"))


def run_job(script, text, env=None):
    """Run one streaming script on `text` (stdin) and return its stdout lines."""
    e = {**os.environ, "LC_ALL": "C", "PYTHONPATH": str(JOBS)}
    e.update(env or {})
    r = subprocess.run([sys.executable, str(JOBS / script)], input=text, capture_output=True,
                       text=True, env=e, check=True)
    return [x for x in r.stdout.splitlines() if x]


def shuffle(lines):
    """Stand-in for Hadoop's sort/shuffle between map and reduce."""
    return "\n".join(sorted(lines)) + "\n"
