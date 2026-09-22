# Medical disclaimer

**This software is not a medical device, does not provide medical advice, and must not be used to
make healthcare decisions.**

**Intended use.** This is educational and research software that lets technically skilled users
inspect data from their own EMAY EMG-10 / Contec PM10. It is not intended for diagnosis, treatment,
monitoring, screening, or any other clinical or medical use, by anyone, including healthcare
professionals.

- **Not a medical device.** It has not been reviewed, cleared or approved by the FDA or any other
  regulator, and it has not been clinically validated. It is not intended to diagnose, treat, cure,
  monitor or prevent any disease or condition.
- **Not medical advice.** The reports, measurements, reference ranges, explanations and device
  findings it displays are informational only. They are not a diagnosis, and they are not a
  substitute for evaluation by a qualified healthcare professional.
- **Results may be wrong.** The EMAY EMG-10 / Contec PM10 is a consumer single-lead handheld ECG.
  Its firmware filters the signal to 1-20 Hz and suppresses small signals, and hand-held recordings
  pick up noise. The device's own findings come from its automated screening and can include false
  alarms and misses. This software's measurements are automated estimates that can be inaccurate
  or missing, and a normal-looking result does not rule out a heart problem. It does not detect
  atrial fibrillation.
- **Do not rely on it.** Do not start, stop or change any treatment or medication, or delay seeking
  care, because of anything this software shows. Always consult a qualified healthcare professional
  about your health.
- **Emergencies.** If you have chest pain, fainting, severe shortness of breath, or any other
  symptom that concerns you, contact emergency services or seek medical care immediately. Do not
  use this software to assess an emergency.
- **Use at your own risk.** You use this software entirely at your own risk and are solely
  responsible for any decisions you make. To the maximum extent permitted by law, the authors and
  contributors accept no liability for any injury, loss, damage or harm, direct or indirect, arising
  from its use or from reliance on its output. See also the warranty disclaimer and limitation of
  liability in [LICENSE](LICENSE).
- **Source code for technically skilled users.** This project is distributed only as source code,
  free of charge and outside any commercial activity, with no packaged application, installer or
  support. Running it requires installing and executing the code yourself. You are responsible for
  reviewing the code and its documented methods and limitations, and for deciding whether it is
  suitable for any purpose.
- **Your environment, your responsibility.** You are responsible for setting up and maintaining a
  hardware and software environment capable of running this code: the computer, operating system,
  USB connection (ports, hubs and cables), the device and its firmware, the Python version, and the
  versions of every library it depends on (such as NeuroKit2, NumPy, SciPy, Matplotlib and hidapi).
  The author has run it only with the library versions pinned in `requirements.txt`, and no
  environment is supported or guaranteed. Differences between environments, including library
  updates, can change beat detection, measurements, plots and device findings as displayed, or
  cause transfer errors or incomplete data, and results may not be reproducible across
  environments. Each report and `index.csv` records the software versions that produced it.
- **Your device, your responsibility.** The software communicates with the device using a
  reverse-engineered protocol. It sends only commands observed from the vendor's own software, but
  it comes with no guarantee of compatibility and no protection against device malfunction or data loss.
- **No affiliation.** This project is not affiliated with, endorsed by or supported by EMAY or
  Contec Medical Systems. Product names are used only to identify compatible hardware.
