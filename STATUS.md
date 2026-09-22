# EMAY EMG-10 ECG tools — status

## Goal
Get recordings off an EMAY EMG-10 handheld ECG (a rebadged **Contec PM10**) without vendor
software, and render readable, labelled plots.

## Milestones
- [x] Device found on USB: Nuvoton "HID Transfer", VID:PID `4444:5555`, 64-byte vendor HID reports
- [x] Protocol decoded by tracing the Contec "Portable ECG Monitor" macOS app with lldb
      (`tools/lldb_capture.py`). Documented in the `emg10.py` docstring.
- [x] `download.py`: sets the device clock on every connect, lists recordings, saves each as CSV + PNG.
      Resumes automatically when the device powers itself off mid-transfer.
- [x] Recordings download to `recordings/` (gitignored: personal health data)
- [x] ECG-paper PNGs with median-beat PR/QRS/QT/QTc labels (`ecg_analysis.py`, `ecg_plot.py`);
      `python download.py --replot` regenerates them from the CSVs without the device
- [x] Beat classification rebuilt (2026-09-22): raw-peak location, feature grouping, T-wave rejection
- [x] Amplitude calibrated (500 counts/mV)
- [x] Plain-language "What these measurements mean" section on each PNG (`ecg_explain.py`): what each
      measure is, typical adult range, and where this recording falls. No range judgement on HR when many beats differ in shape.
- [ ] Noise robustness: per-segment quality, grey 'possible artifact' for one-off odd complexes (proposed, not started)

## Key facts
- 250 Hz, 30 s = 7500 samples, 14-bit values sent as two 7-bit bytes; baseline 8192
- **1 mV = 500 counts**: calibrated by measuring a screenshot of the Contec app at 10 mm/mV
  (R and S amplitudes agree within 5%). Reading the app's disassembly gave 5000, which was off by 10x.
- The firmware zeroes small signals (noise gate), so P waves are usually invisible
- Recording 1 = newest. The Contec app's "delete" only affects its own database. No
  device delete command was ever observed, and our code never sends unknown commands.
- The EMAY ECG HD app (for EMG-6L/20) uses the same VID/PID but a different protocol and rejects the EMG-10

## Open threads
- Beat classification: beats are located on the raw signal, grouped by polarity, amplitude (2x),
  width (1.5x) and loose shape correlation, and the narrowest large group is the "reference" shape.
  Same-polarity small detections within 450 ms of a reference beat are dropped as T waves.
  The report shows both the all-beat rate and the reference-beat rate, next to the device's figure.
  - Validation: on clean recordings (<= 2 other-shape beats) the all-beat rate matches the device's HR
    within 3 bpm. On mixed recordings the device's HR usually falls between our two rates; its
    counting rule is unknown, so it's not used as ground truth there.
  - QT is skipped when fewer than 5 reference beats are free of other-shape neighbours, or when it
    falls outside 260-600 ms (T wave misidentified). PR is rarely measurable (noise gate).
  - Remaining weak spot: noisy recordings with ambiguous small complexes
- Device result codes (header bytes 16–17): the Contec app labels code 1 "Missed Beat".
  The other codes are unmapped. A table could be built by comparing more recordings in the app.
- `main.py` is an unused FastAPI stub from project creation
- Personal recording metrics live in `STATUS.local.md` (gitignored)
