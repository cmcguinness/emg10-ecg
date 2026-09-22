"""Render docs/example_report.png from a simulated ECG (no real recording involved).

The simulated signal is band-passed to 1-20 Hz and converted to device counts so it goes
through the same analysis and rendering as a real EMG-10 recording.

Usage: python tools/make_example.py
"""
import sys
import warnings
from pathlib import Path

import neurokit2 as nk
import numpy as np
from scipy.signal import butter, filtfilt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ecg_analysis import COUNTS_PER_MV, FS, analyze  # noqa: E402
from ecg_plot import render  # noqa: E402


def main():
    warnings.filterwarnings("ignore")
    mv = nk.ecg_simulate(duration=30, sampling_rate=FS, heart_rate=72, noise=0.01,
                         method="ecgsyn", random_state=7)
    b, a = butter(2, [1, 20], btype="band", fs=FS)       # the device's pass band
    mv = filtfilt(b, a, mv)
    counts = np.clip(np.round(mv * COUNTS_PER_MV + 8192), 0, 16383).astype(int)

    out = ROOT / "docs" / "example_report.png"
    out.parent.mkdir(exist_ok=True)
    render(out, analyze(counts), "Example report  -  simulated ECG, not a real recording",
           result_codes=(0, 0))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
