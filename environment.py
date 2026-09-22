"""The software environment that produced a result, recorded on every report and in index.csv."""
from __future__ import annotations

import importlib.metadata
import platform
import subprocess
from functools import lru_cache
from pathlib import Path

PROJECT_VERSION = "0.1.0"
_LIBS = ("neurokit2", "numpy", "scipy", "matplotlib", "pandas")


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "describe", "--always", "--dirty"], cwd=Path(__file__).parent,
                             capture_output=True, text=True, timeout=2)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


@lru_cache(maxsize=1)
def versions() -> dict[str, str]:
    v = {"emg10-ecg": PROJECT_VERSION, "python": platform.python_version()}
    commit = _git_commit()
    if commit:
        v["commit"] = commit
    for lib in _LIBS:
        try:
            v[lib] = importlib.metadata.version(lib)
        except importlib.metadata.PackageNotFoundError:
            v[lib] = "not installed"
    return v


def summary() -> str:
    """One line, e.g. 'emg10-ecg 0.1.0 (abc1234) | Python 3.13.15 | neurokit2 0.2.13 | ...'."""
    v = dict(versions())
    head = f"emg10-ecg {v.pop('emg10-ecg')}" + (f" ({v.pop('commit')})" if "commit" in v else "")
    return " | ".join([head, f"Python {v.pop('python')}"] + [f"{k} {val}" for k, val in v.items()])
