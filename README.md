# EMG-10 ECG tools

Download and read recordings from an **EMAY EMG-10** handheld ECG (a rebadged **Contec PM10**)
over USB, without the vendor software, and render them as labelled ECG-paper PNGs.

- `emg10.py`: the device's USB HID protocol (reverse-engineered; documented in the module docstring)
- `download.py`: syncs the device clock, lists and downloads recordings to CSV + PNG
  (`--list`, `--record N`, `--replot`)
- `ecg_analysis.py`, `ecg_plot.py`, `ecg_explain.py`: beat detection, interval estimates, and reports
- `tools/`: HID capture/probe utilities used during reverse engineering

```
pip install -r requirements.txt
python download.py            # turn the device on and connect USB when prompted
```

## Disclaimer

This is not a medical device, and nothing it produces is a diagnosis. The EMG-10 is a consumer
single-lead handheld ECG: it filters the signal to 1-20 Hz (diagnostic ECGs record roughly
0.05-150 Hz), suppresses small signals, and picks up noise from hand contact, which distorts wave
shapes and interval measurements. The device's own findings come from its automated screening and
can include false alarms and misses. It has no atrial fibrillation detection. The measurements
this software adds are automated estimates that have not been clinically validated. Discuss any
results with a clinician, and seek urgent care for symptoms such as chest pain, fainting or severe
breathlessness.

Only known commands are ever sent to the device. It is not affiliated with EMAY or Contec.
