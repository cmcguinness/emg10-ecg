# Methods

How a downloaded recording becomes a report: which steps use **NeuroKit2**, which use this project's
own code, and why. All numbers below are the values in the code (`ecg_analysis.py`, `ecg_explain.py`).
These are automated estimates from software that has not been clinically validated; see
[DISCLAIMER.md](DISCLAIMER.md).

## At a glance

| Step | Done by | Where |
|---|---|---|
| Convert raw counts to millivolts | this project | `ecg_analysis.to_mv` |
| Filter for beat detection | **NeuroKit2** `ecg_clean` | `ecg_analysis.analyze` |
| Find beats | **NeuroKit2** `ecg_peaks` (Elgendi 2010 detector) | `ecg_analysis.detect_beats` |
| Re-centre beats on the raw signal, merge duplicates | this project | `ecg_analysis.detect_beats` |
| Group beats by shape | this project | `ecg_analysis.classify` |
| Drop T waves counted as beats | this project | `ecg_analysis._drop_t_wave_detections` |
| Heart rates, rhythm variation, "check" sections | this project | `ecg_analysis` |
| Median beat and PR / QRS / QT / QTc | this project | `ecg_analysis.analyze` and helpers |
| Typical ranges and explanations | this project | `ecg_explain.py` |
| Device findings | the device (decoded here) | `emg10.DEVICE_FINDINGS` |
| Synthetic example for the README | **NeuroKit2** `ecg_simulate` | `tools/make_example.py` |

In short: **NeuroKit2 finds the beats; everything after that is this project's code.**

## What the device gives us

Each recording is 7,500 samples at **250 Hz** (30 s), 14-bit values with a baseline of 8192. The
device's firmware has already filtered the signal to **1-20 Hz** and zeroes out small signals (a noise
gate) before storing it; there is no unfiltered mode. These properties shape most of the choices below:
the filtering blunts the edges of each beat, and the noise gate usually removes the P wave.

## 1. Scale

`mV = (raw - 8192) / 500`. The scale of **500 counts per mV** was calibrated against the Contec app's
display at its standard 10 mm/mV setting: two independent measurements agreed within 5%. An earlier
estimate of 5,000, read from the app's disassembled drawing code, was wrong by a factor of 10.

## 2. Beat detection (NeuroKit2)

1. **Cleaning:** `nk.ecg_clean` with its default method: a 0.5 Hz high-pass filter (5th-order
   Butterworth) to remove drift, then a mains-hum filter. The cleaned signal is used only to find
   beats; all measurements use the millivolt signal as stored by the device, without this extra cleaning.
2. **Detection:** `nk.ecg_peaks` with the **Elgendi (2010)** detector. It responds to signal energy
   rather than direction, so it finds beats that point up or down.
3. **Re-centring (own code):** each detection is moved to the largest deflection in the raw signal
   within ±150 ms. Detections of wide beats often land on the upswing after them.
4. **Merging (own code):** detections less than 200 ms apart are merged, keeping the larger deflection.

## 3. Grouping beats by shape (own code)

Two beats are "the same shape" when **all** of these hold:
- same polarity (both up or both down),
- amplitude within **2×** of each other,
- width within **1.5×** (width = span of the main deflection above 30% of its peak),
- correlation of their ±60 ms waveforms **≥ 0.5**.

Groups are seeded from the largest deflections first. The **reference** group is the narrowest group
that holds at least 20% of the beats (and at least 3). Other groups with two or more members are
"other shape" (orange on the report); a shape seen only once is **one-off** (grey), because a single
example can't separate a lone early beat from a movement or contact artifact.

**T-wave rejection:** a non-reference detection is dropped as a T wave if it has the reference
polarity, is under **45%** of the reference height, and falls within **450 ms** after a reference beat.
Opposite-polarity deflections are kept, because they're usually real beats.

This grouping describes shape only. It is not a clinical beat classification.

## 4. Rates and rhythm

- **Heart rate:** (beats − 1) × 60 / (time from first to last beat), counting reference and recurring
  other-shape beats and leaving out one-offs.
- **Reference-beat rate:** the same, counting reference beats only. When 20% or more of beats have
  another shape, the report shows both counts and doesn't compare either with the typical range.
- **RR (median):** median interval between *consecutive* reference beats; used for QTc.
- **Rhythm variation:** coefficient of variation (%) and RMSSD of consecutive reference-beat intervals.
  It needs at least 5 intervals. Labels: < 5% steady, 5-10% some variation, > 10% marked.
- **"Check" sections:** 2-second windows whose mean sample-to-sample change *outside* the QRS
  complexes (±80 ms around each beat) exceeds **4.5%** of the reference height, about the top 1% of
  windows across the recordings used for development. They are shaded for review and never excluded,
  because unusual beats can look "busy" too.

## 5. Median beat and intervals (own code)

NeuroKit2's delineator (`ecg_delineate`) was tried and rejected: on this device's signal it reported
QRS widths of 150-180 ms for complexes about 50 ms wide. Intervals are measured on a **median beat**
instead, which averages away much of the noise.

1. **Which beats:** reference beats with a window of −350 ms to +600 ms around R that contains no other-
   shape beat (with 100 ms extra margin for its width). At least **5** such beats are needed to measure
   P and T; otherwise only QRS is reported, with a note.
2. **Median beat:** each beat is baseline-corrected on its first 50 ms, then the sample-wise median is
   taken.
3. **QRS onset and offset:** where the slope rises above / falls below **10%** of the steepest slope
   within ±120 ms of R.
4. **T wave:** the median beat is smoothed over 40 ms, then the T peak is the largest deflection from
   60 ms after QRS offset until the earlier of +500 ms and 75% of the RR interval. It must reach at least
   **15%** of the beat's largest deflection. **T end** uses the **tangent method**: the steepest slope on
   the T wave's trailing limb is extended to the baseline.
5. **QT plausibility:** a QT outside **260-600 ms** means the T wave was almost certainly misidentified,
   so it is reported as "not measured (T wave ambiguous)".
6. **P wave:** the largest deflection 300 to 40 ms before QRS onset, accepted only if it exceeds both 4×
   the beat-to-beat noise and 8% of the largest deflection. P onset is where it falls below 20% of its
   peak. Because of the device's noise gate, this rarely succeeds.
7. **Intervals:** PR = P onset → QRS onset; QRS = onset → offset; QT = QRS onset → T end.
   **QTc (Bazett)** = QT / √RR; **QTc (Fridericia)** = QT / ∛RR (RR in seconds).

## 6. Typical ranges (`ecg_explain.py`)

Common adult resting values from general clinical references: heart rate 60-100 bpm, PR 120-200 ms,
QRS 80-100 ms (under 120 considered normal), QTc 350-450 ms (up to about 460 is often used for women;
over 500 markedly long). The **typical QT for a recording** is the QTc range converted back through
Bazett at that recording's RR: 350·√RR to 450·√RR.

## 7. Validation and known weaknesses

- **Heart rate:** on recordings with at most two other-shape beats, the heart rate is within 3 bpm of
  the device's own figure on 94% of them. On mixed recordings the device follows an unknown counting rule, so it
  isn't used as ground truth there.
- **QRS is noise-sensitive:** on one simulated beat shape it measures 88-148 ms depending only on the
  random noise. QRS also tends to read short on this device, because of the 1-20 Hz filtering.
- **PR is rarely measurable**, because the noise gate removes most P waves.
- **No atrial fibrillation detection.** Recognising AF relies on missing P waves and irregular beat
  spacing; here the noise gate removes P waves anyway, and other-shape beats make spacing irregular
  on their own.
- **NeuroKit2's quality score** (`ecg_quality`) was tried and didn't distinguish noisy recordings on
  this device, so it isn't used.
- **Versions matter:** detector behaviour can change between NeuroKit2 releases. The tested versions
  are pinned in `requirements.txt`, and every report's footer records the versions that produced it.

## References

- Makowski, D., et al. (2021). NeuroKit2: A Python toolbox for neurophysiological signal processing.
  *Behavior Research Methods*, 53, 1689-1696.
- Elgendi, M., et al. (2010). Frequency bands effects on QRS detection. *BIOSIGNALS 2010*.
