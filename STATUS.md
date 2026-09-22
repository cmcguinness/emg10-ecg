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
- [x] Device findings decoded and shown on reports (code table from the Contec app's Feature.plist; `emg10.DEVICE_FINDINGS`)
- [x] Rhythm variation (CV %, RMSSD) of consecutive main beats; accuracy disclaimer on reports + README
- [x] Noise handling, flag-don't-exclude: 2 s windows with high between-beat activity are shaded 'check'
      (can be noise or a run of unusual beats, so never excluded); one-off shapes are grey. Hard dropouts are rare.

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
  - Heart rate counts reference + recurring other-shape beats; one-off shapes (seen once) are grey
    and not counted. Validation: on clean recordings (<= 2 other-shape beats) it matches the device's HR
    within 3 bpm on 94%. On mixed recordings the device's HR usually falls between our two rates; its
    counting rule is unknown, so it's not used as ground truth there.
  - QT is skipped when fewer than 5 reference beats are free of other-shape neighbours, or when it
    falls outside 260-600 ms (T wave misidentified). PR is rarely measurable (noise gate).
  - Remaining weak spot: noisy recordings with ambiguous small complexes
  - QRS duration is noise-sensitive: on one simulated beat shape it reads 88-148 ms depending only on
    the noise seed (slope-threshold onset/offset). A more robust QRS delineation would help.
- Device result codes (header bytes 16-17) are decoded: 0 No abnormal ... 11 Arrhythmia, 12/13 ST changes.
  The device has **no atrial fibrillation category**, and we don't attempt AF detection: P waves are lost to the
  noise gate and other-shape beats confound RR irregularity.
- Raw/unfiltered data: not available over USB. The settings command (0x83) covers language/beep only (the
  Contec app exposes no filter option). Filtering and the noise gate happen in firmware before storage;
  the only route would be hardware (the MCU's debug port or tapping the analog front end). Not pursued.
- Personal recording metrics live in `STATUS.local.md` (gitignored)
