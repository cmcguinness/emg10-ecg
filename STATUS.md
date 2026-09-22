# EMAY EMG-10 ECG tools — status

## Goal
Get recordings off an EMAY EMG-10 handheld ECG (a rebadged **Contec PM10**) without vendor
software, and render readable, labelled plots.

## Milestones
- [x] Device found on USB: Nuvoton "HID Transfer", VID:PID `4444:5555`, 64-byte vendor HID reports
- [x] Protocol decoded by tracing the Contec "Portable ECG Monitor" macOS app with lldb
      (`tools/lldb_capture.py`). Documented in the `emg10.py` docstring.
- [x] `download.py`: sets the device clock (always), lists recordings, saves each as CSV + PNG.
      Resumes automatically when the device powers itself off mid-transfer.
- [x] All 96 recordings downloaded to `recordings/` (gitignored: personal health data)
- [x] ECG-paper PNGs with median-beat PR/QRS/QT/QTc labels (`ecg_analysis.py`, `ecg_plot.py`);
      `python download.py --replot` regenerates them from the CSVs without the device
- [ ] Better beat classification (see open threads)
- [x] Amplitude calibrated (500 counts/mV)

## Key facts
- 250 Hz, 30 s = 7500 samples, 14-bit values sent as two 7-bit bytes; baseline 8192
- **1 mV = 500 counts**: calibrated by measuring a screenshot of the Contec app at 10 mm/mV
  (R and S amplitudes agree within 5%). My reading of the app's
  disassembly gave 5000, which was off by 10x.
- The firmware zeroes small signals (noise gate), so P waves are usually invisible
- Recording 1 = newest. The Contec app's "delete" only affects its own database. No
  device delete command was ever observed, and our code never sends unknown commands.
- The EMAY ECG HD app (for EMG-6L/20) uses the same VID/PID but a different protocol and rejects the EMG-10

## Open threads
- 64 of 96 recordings contain many beats with a different shape. The simple correlation grouping
  misclassifies some of them. Beat classification is cross-checked against the device's HR (±8 bpm);
  when they disagree, intervals are withheld. Result: 61 recordings with QT, 8 QRS only, 27 withheld.
  Heart rate matches the device within 3 bpm on 91% of the clean recordings.
- Device result codes (header bytes 16–17): the Contec app shows codes (1, 0) as "Missed Beat".
  The other codes are unmapped. A table could be built by comparing more recordings in the app.
- `main.py` is an unused FastAPI stub from project creation
