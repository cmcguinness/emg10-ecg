# EMAY EMG-10 ECG tools: status

**State: complete (v0.1.0), public.** Repo: https://github.com/cmcguinness/emg10-ecg ·
Article: https://mcguinnessai.substack.com/p/using-ai-to-rescue-old-hardware

## Goal
Get recordings off an EMAY EMG-10 handheld ECG (a rebadged **Contec PM10**) without vendor software,
since the vendor's Intel-only Mac app won't open on macOS 28, and render readable, labelled reports.

## Done
- **Protocol** decoded by tracing the Contec "Portable ECG Monitor" app with lldb (`tools/lldb_capture.py`);
  documented in `emg10.py` and the README
- **Downloader** (`download.py`): sets the device clock on every connect, lists and downloads recordings to
  CSV + PNG, and resumes when the device powers off mid-transfer. Exits cleanly if no device appears.
  `--replot` regenerates reports from CSVs.
- **Reports**: ECG paper at 25 mm/s, calibrated at 500 counts/mV; beat grouping (reference / other shape /
  one-off); PR/QRS/QT/QTc on a median beat; rhythm variation; "check" sections flagged, never excluded;
  the device's own findings decoded; plain-language explanations with typical ranges
- **Docs**: README, [METHODS.md](METHODS.md) (every step and threshold, validation, weaknesses),
  [BACKSTORY.md](BACKSTORY.md) (how it was built), [DISCLAIMER.md](DISCLAIMER.md)
- **Release hygiene**: MIT-0 license; medical disclaimer, intended-use statement, and a one-time
  acknowledgement on first run (`acknowledge.py`); pinned tested versions; every report records the
  software versions behind it (`environment.py`); no personal data in any commit; commits use a GitHub
  noreply address; a fresh-clone install was verified before going public

## Key facts
- 250 Hz, 30 s = 7,500 samples; 14-bit values sent as two 7-bit bytes; baseline 8192; 500 counts/mV
- The firmware filters to 1-20 Hz and zeroes small signals (noise gate), so P waves are usually lost;
  there is no raw mode over USB
- Recording 1 = newest. The Contec app's "delete" only affects its own database. Our code never sends
  unknown commands and has no delete.
- EMAY ECG HD (for the EMG-6L/20) uses the same USB IDs but a different protocol, and rejects the EMG-10
- The Contec app runs natively on an Intel Mac; after macOS 28 that's the only way to run it, e.g. for
  further protocol tracing

## Known limitations / possible future work
- QRS duration is noise-sensitive (88-148 ms on one simulated beat shape depending on noise); a more robust
  QRS delineation would help
- Noisy recordings with ambiguous small complexes: beat vs T wave can be misjudged
- No atrial fibrillation detection (the device has none, and P waves are lost)
- Tested on macOS (Apple silicon) with Python 3.13 only; Linux and Windows untested (Linux will likely
  need a udev rule for USB HID access)
- The device's "Delete all" command was never captured (intentionally unused)

## Resuming
- `pip install -r requirements.txt`, then `python download.py`. The first run asks you to accept
  DISCLAIMER.md. Editing DISCLAIMER.md makes every user re-accept.
- Personal recording metrics live in `STATUS.local.md` (gitignored)
