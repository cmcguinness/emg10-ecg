"""Plain-language explanations of the measurements in a recording's report.

Reference ranges are common adult resting values from general clinical references.
They are context for reading the numbers, not a diagnosis; a single handheld lead-I
recording can over- or under-estimate every one of them.
"""
from __future__ import annotations

from ecg_analysis import Analysis
from emg10 import finding_labels

# (low, high) typical adult resting ranges
HR_RANGE = (60, 100)        # bpm
PR_RANGE = (120, 200)       # ms
QRS_TYPICAL = (80, 100)     # ms
QRS_MAX = 120               # ms; under this is considered normal
QTC_RANGE = (350, 450)      # ms (Bazett); up to ~460 is often used for women, >500 is markedly long

CONFIRM = "A single handheld reading can be off; worth confirming on a clinical ECG."

# Plain-language meaning of the device's own findings (see emg10.DEVICE_FINDINGS)
FINDING_TEXT = {
    "No abnormal": "the device's screening found nothing it flags",
    "Missed Beat": "an unexpectedly long gap where a beat would normally occur",
    "Accidental VPB": "an occasional ventricular premature beat (VPB): an early beat starting in the lower chambers",
    "VPB Trigeminy": "a ventricular premature beat on every third beat",
    "VPB Bigeminy": "a ventricular premature beat alternating with every normal beat",
    "VPB Couple": "two ventricular premature beats in a row",
    "VPB runs of 3": "three ventricular premature beats in a row",
    "VPB runs of 4": "four ventricular premature beats in a row",
    "VPB RonT": "a premature beat landing on the T wave of the previous beat",
    "Bradycardia": "a slow heart rate (usually under 60 bpm)",
    "Tachycardia": "a fast heart rate (usually over 100 bpm)",
    "Arrhythmia": "an irregular rhythm; a general flag that includes common benign irregularity",
    "ST Elevation": "the segment after the QRS sits above baseline",
    "ST Depression": "the segment after the QRS sits below baseline",
}

ACCURACY = (
    "This is a consumer single-lead handheld ECG. The device filters the signal to 1-20 Hz (diagnostic "
    "ECGs record roughly 0.05-150 Hz), suppresses small signals, and hand contact adds noise, all of which "
    "distort wave shapes and interval measurements (QRS tends to read short; P waves are usually lost). The "
    "device's findings come from its own automated screening and can include false alarms and misses; it "
    "has no atrial fibrillation detection. The measurements in this report come from software that has not "
    "been clinically validated. This is not a medical device or a diagnosis: discuss results with a "
    "clinician, and seek urgent care for symptoms such as chest pain, fainting or severe breathlessness.")


def variation_label(cv: float) -> str:
    return "steady" if cv < 5 else ("some variation" if cv < 10 else "marked variation")


def qt_range_for(rr_s: float) -> tuple[float, float]:
    """Typical QT at this RR, from the typical QTc range inverted through Bazett."""
    return QTC_RANGE[0] * rr_s ** 0.5, QTC_RANGE[1] * rr_s ** 0.5


def typical(a: Analysis) -> dict[str, str]:
    """Typical-range strings for the summary table, keyed by measurement."""
    t = {"HR": f"{HR_RANGE[0]}-{HR_RANGE[1]} bpm", "PR": f"{PR_RANGE[0]}-{PR_RANGE[1]} ms",
         "QRS": f"{QRS_TYPICAL[0]}-{QRS_TYPICAL[1]} ms (<{QRS_MAX})", "QTc": f"{QTC_RANGE[0]}-{QTC_RANGE[1]} ms"}
    if a.rr_s:
        lo, hi = qt_range_for(a.rr_s)
        t["QT"] = f"{lo:.0f}-{hi:.0f} ms at this rate"
    return t


def _where(v: float, lo: float | None, hi: float | None) -> str:
    if lo is not None and v < lo:
        return f"below the typical range. {CONFIRM}"
    if hi is not None and v > hi:
        return f"above the typical range. {CONFIRM}"
    return "within the typical range."


def explain(a: Analysis, device_hr: int | None = None,
            result_codes: tuple[int, int] | None = None) -> list[tuple[str, str]]:
    iv = a.intervals_ms
    out: list[tuple[str, str]] = []

    hr, ref = a.heart_rate, a.reference_rate
    mixed = a.n_other >= 0.2 * max(len(a.r_peaks), 1)
    if hr and mixed and ref:
        txt = (f"Beats per minute. Typical resting range {HR_RANGE[0]}-{HR_RANGE[1]} bpm. Many beats in this "
               f"recording have a different shape, so the rate depends on which are counted: {hr:.0f} per "
               f"minute counting all recurring shapes, {ref:.0f} per minute counting only the main shape. It isn't "
               f"compared with the typical range for that reason.")
    elif hr:
        txt = (f"Beats per minute. Typical resting range {HR_RANGE[0]}-{HR_RANGE[1]} bpm. "
               f"This recording: {hr:.0f} bpm, {_where(hr, *HR_RANGE)}")
        if a.n_other and ref and abs(ref - hr) >= 3:
            txt += f" Counting only the main (reference) beat shape: {ref:.0f} per minute."
    if hr:
        if device_hr:
            txt += f" The device reported {device_hr} bpm"
            lo, hi = sorted((hr, ref or hr))
            if lo + 3 < device_hr < hi - 3:
                txt += ", between the two, so it evidently counts only some of the other-shape beats"
            txt += "."
        out.append(("Heart rate", txt))

    if result_codes:
        labels = finding_labels(result_codes)
        parts = [f"{lab}: {FINDING_TEXT.get(lab, 'no description available')}" for lab in labels]
        out.append(("Device's finding",
                    "The device runs its own automated screening on each recording. It reported "
                    + "; ".join(parts) + ". This is the device's label, not a diagnosis."))

    if a.rr_cv is not None:
        txt = (f"How much the spacing between consecutive main beats varies (other-shape beats are left out). "
               f"Here: {a.rr_cv:.1f}% variation ({variation_label(a.rr_cv)})")
        if a.rr_rmssd_ms is not None:
            txt += f", RMSSD {a.rr_rmssd_ms:.0f} ms"
        txt += (". Some variation is normal: the rate rises and falls with breathing, and resting RMSSD in "
                "healthy adults is often around 20-60 ms, lower with age. Under 5% is steady, 5-10% moderate, "
                "over 10% marked. Irregular spacing can come from breathing, premature beats, or rhythm "
                "disturbances, or from missed beat detections in a noisy recording, so this is descriptive only.")
        out.append(("Rhythm variation", txt))

    if a.rr_s:
        out.append(("RR interval",
                    f"Time from one beat to the next ({a.rr_s * 1000:.0f} ms here, the median between "
                    f"consecutive main-shape beats). It is the basis for heart rate (60,000 / RR) and "
                    f"for correcting QT."))

    if "PR" in iv:
        out.append(("PR interval",
                    f"Start of atrial activation (P wave) to start of ventricular activation (QRS): how "
                    f"long the impulse takes to pass from the upper to the lower chambers. Typical "
                    f"{PR_RANGE[0]}-{PR_RANGE[1]} ms. This recording: {iv['PR']:.0f} ms, "
                    f"{_where(iv['PR'], *PR_RANGE)}"))
    else:
        out.append(("PR interval",
                    "Start of the P wave (atrial activation) to start of the QRS. Not measured here: "
                    "the P wave is small, and this device's noise suppression usually flattens it."))

    if "QRS" in iv:
        q = iv["QRS"]
        txt = (f"How long the ventricles take to activate, the sharp spike of each beat. Typically "
               f"{QRS_TYPICAL[0]}-{QRS_TYPICAL[1]} ms in adults; under {QRS_MAX} ms is considered normal. "
               f"This recording: {q:.0f} ms, ")
        if q >= QRS_MAX:
            txt += f"above the normal limit. {CONFIRM}"
        elif q > QRS_TYPICAL[1]:
            txt += f"above the typical {QRS_TYPICAL[1]} ms but under the {QRS_MAX} ms limit."
        elif q < QRS_TYPICAL[0]:
            txt += ("below the typical range. That is common on handheld devices: the 1-20 Hz filtering "
                    "blunts the edges of the spike, so QRS tends to read short.")
        else:
            txt += "within the typical range."
        out.append(("QRS duration", txt))

    if "QT" in iv:
        qtc = iv.get("QTcB")
        txt = (f"Start of the QRS to the end of the T wave: the ventricles' full activate-and-recover "
               f"cycle. QT naturally shortens as heart rate rises (roughly 350-450 ms at 60 bpm).")
        if a.rr_s:
            lo, hi = qt_range_for(a.rr_s)
            txt += (f" At this recording's rate ({60 / a.rr_s:.0f} bpm between main beats) a typical QT is "
                    f"about {lo:.0f}-{hi:.0f} ms. This recording: {iv['QT']:.0f} ms, {_where(iv['QT'], lo, hi)}")
        else:
            txt += f" This recording: {iv['QT']:.0f} ms."
        out.append(("QT interval", txt))
        if qtc:
            out.append(("QTc",
                        f"QT corrected for heart rate. Bazett {qtc:.0f} ms, Fridericia {iv['QTcF']:.0f} ms "
                        f"(Fridericia is less distorted at fast or slow rates). Typical about "
                        f"{QTC_RANGE[0]}-{QTC_RANGE[1]} ms (up to ~460 ms is often used for women; over "
                        f"500 ms is considered markedly long). This recording: "
                        f"{_where(qtc, *QTC_RANGE)}"))
    else:
        out.append(("QT / QTc",
                    "Start of the QRS to the end of the T wave, corrected for heart rate. Not measured "
                    "here: " + (a.notes[-1].split(": ", 1)[-1] if a.notes else "T wave not identifiable") + "."))

    if a.n_other:
        out.append(("Other-shape beats",
                    f"{a.n_other} of {len(a.r_peaks)} beats (orange) have a different shape from the main "
                    f"beats (blue), and that shape recurs. Beats with a different shape can come from a "
                    f"different origin in the heart, such as early (premature) beats; a shape that repeats "
                    f"consistently is less likely to be a movement or contact artifact."))
    if a.n_one_off:
        out.append(("One-off shapes",
                    f"{a.n_one_off} complex(es) (grey) have a shape seen only once in this recording. From a "
                    f"single example there is no telling a lone early beat from a movement or contact "
                    f"artifact, which is common when a device is held between two hands. They are not counted in "
                    f"the heart rate."))
    if a.busy:
        spans = ", ".join(f"{b0:.0f}-{b1:.0f} s" for b0, b1 in a.busy)
        out.append(("Check sections",
                    f"{spans}: unusually high activity between beats (shaded). This can be noise or poor "
                    f"contact, or a run of unusual beats. Nothing was excluded; look at the trace there."))

    out.append(("Accuracy", ACCURACY))
    out.append(("About the ranges", "Typical adult resting values from general clinical references; "
                "individual normal values vary with age, sex, fitness and medication."))
    return out
