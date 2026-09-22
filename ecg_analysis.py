"""Beat detection and interval measurement for single-lead EMG-10 recordings.

Beats are found with NeuroKit2. Intervals are measured on the median beat of the
dominant beat shape, because the device's output (1-20 Hz band, 250 Hz, and a firmware
noise gate that flattens small signals to exactly zero) defeats per-beat delineators:

  QRS onset/offset  where the slope of the median beat rises above / falls below 10%
                    of its peak QRS slope
  T end             tangent method: steepest slope of the T wave's trailing limb,
                    extrapolated to the baseline
  P onset           only when a P wave clearly exceeds the noise floor; otherwise None

These are automated estimates, not a diagnosis.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import neurokit2 as nk
import numpy as np

FS = 250
COUNTS_PER_MV = 500    # calibrated against the Contec app drawn at 10 mm/mV (R and S waves agree within 5%)
PRE_S, POST_S = 0.35, 0.60   # median-beat window around R
MIN_CLEAN_BEATS = 5          # beats with no different-shape neighbour needed to measure P and T
HR_TOLERANCE = 8             # bpm; larger disagreement with the device = unreliable beat grouping


@dataclass
class Fiducials:
    """Sample indices within the median beat (R peak is at index `r`)."""
    r: int
    qrs_on: int
    qrs_off: int
    t_peak: int | None = None
    t_end: int | None = None
    p_peak: int | None = None
    p_on: int | None = None


@dataclass
class Analysis:
    mv: np.ndarray                      # full recording, mV
    r_peaks: np.ndarray                 # all detected beats (sample index)
    dominant: np.ndarray                # bool mask over r_peaks
    template: np.ndarray | None         # median dominant beat, mV
    fid: Fiducials | None
    rr_s: float | None                  # median RR between consecutive dominant beats
    intervals_ms: dict = field(default_factory=dict)   # PR, QRS, QT, QTcB, QTcF
    notes: list[str] = field(default_factory=list)     # why a measurement was skipped

    @property
    def heart_rate(self) -> float | None:
        return 60 / self.rr_s if self.rr_s else None

    @property
    def n_other(self) -> int:
        return int((~self.dominant).sum())


def to_mv(raw_counts) -> np.ndarray:
    return (np.asarray(raw_counts, float) - 8192) / COUNTS_PER_MV


def detect_beats(clean: np.ndarray) -> np.ndarray:
    # Energy-based detector finds beats of either polarity; snap each detection to the
    # largest deflection within +-60 ms.
    r = np.asarray(nk.ecg_peaks(clean, sampling_rate=FS, method="elgendi2010")[1]["ECG_R_Peaks"])
    w = int(0.06 * FS)
    r = np.array([max(p - w, 0) + int(np.argmax(np.abs(clean[max(p - w, 0):p + w]))) for p in r])
    return np.unique(r)


def classify(clean: np.ndarray, r: np.ndarray, thresh: float = 0.8) -> np.ndarray:
    """Mask of beats belonging to the largest group of mutually similar QRS shapes."""
    w = int(0.1 * FS)
    ok = (r >= w) & (r < len(clean) - w)
    seg = np.array([clean[p - w:p + w] for p in r[ok]])
    dom = np.zeros(len(r), bool)
    if len(seg) < 3:
        dom[ok] = True
        return dom
    with np.errstate(invalid="ignore"):
        c = np.nan_to_num(np.corrcoef(seg))
    seed = int(np.argmax((c > thresh).sum(1)))
    dom[np.flatnonzero(ok)] = c[seed] > thresh
    return dom


def _qrs_bounds(s: np.ndarray, r: int) -> tuple[int, int]:
    d = np.abs(np.diff(s))
    lo, hi = max(r - int(0.12 * FS), 1), min(r + int(0.12 * FS), len(d) - 1)
    thr = 0.1 * d[lo:hi].max()
    on = r
    while on > lo and (d[on - 1] > thr or d[on - 2] > thr):
        on -= 1
    off = r
    while off < hi and (d[off] > thr or d[off + 1] > thr):
        off += 1
    return on, off


def _t_wave(s: np.ndarray, qrs_off: int, rr: int) -> tuple[int | None, int | None]:
    start = qrs_off + int(0.06 * FS)
    stop = min(qrs_off + int(0.5 * FS), qrs_off + int(0.75 * rr), len(s) - 2)
    if stop - start < 5:
        return None, None
    seg = s[start:stop]
    tp = start + int(np.argmax(np.abs(seg)))
    amp = s[tp]
    if abs(amp) < 0.15 * np.max(np.abs(s)):
        return None, None
    # tangent method on the trailing limb
    slope = np.diff(s[tp:stop + 1]) * np.sign(amp)
    if len(slope) < 2 or slope.min() >= 0:
        return tp, None
    k = int(np.argmin(slope))
    x0, y0, m = tp + k, s[tp + k], s[tp + k + 1] - s[tp + k]
    t_end = int(round(x0 - y0 / m)) if m else None
    if t_end is None or not (tp < t_end < len(s)):
        return tp, None
    return tp, t_end


def _p_wave(s: np.ndarray, qrs_on: int, noise: float) -> tuple[int | None, int | None]:
    lo, hi = max(qrs_on - int(0.30 * FS), 0), qrs_on - int(0.04 * FS)
    if hi - lo < 5:
        return None, None
    pk = lo + int(np.argmax(np.abs(s[lo:hi])))
    amp = abs(s[pk])
    if amp < max(4 * noise, 0.08 * np.max(np.abs(s))):
        return None, None
    on = pk
    while on > lo and abs(s[on]) > 0.2 * amp:
        on -= 1
    return pk, on


def analyze(raw_counts, device_hr: int | None = None) -> Analysis:
    """device_hr, when given, is used as a cross-check: if our beat detection disagrees
    with the device by more than HR_TOLERANCE bpm, intervals are withheld."""
    mv = to_mv(raw_counts)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        clean = nk.ecg_clean(mv, sampling_rate=FS)
    r = detect_beats(clean)
    if len(r) < 3:
        return Analysis(mv, r, np.ones(len(r), bool), None, None, None)
    dom = classify(clean, r)
    pre, post = int(PRE_S * FS), int(POST_S * FS)
    rd = r[dom]
    rd_ok = rd[(rd >= pre) & (rd < len(mv) - post)]
    # RR only between consecutive beats that are both dominant
    rr = [b - a for a, b, da, db in zip(r, r[1:], dom, dom[1:]) if da and db]
    rr_s = float(np.median(rr)) / FS if rr else None
    if len(rd_ok) < 3:
        return Analysis(mv, r, dom, None, None, rr_s)

    # P and T are only measurable on beats with no different-shape beat nearby; otherwise
    # the median beat mixes in the neighbouring complex.
    # Detections of wide beats often land on their trailing upswing, so re-centre them on
    # the largest raw deflection nearby and allow for their width.
    w, margin = int(0.15 * FS), int(0.1 * FS)
    others = np.array([max(p - w, 0) + int(np.argmax(np.abs(mv[max(p - w, 0):p + w]))) for p in r[~dom]])
    isolated = np.array([not np.any((others > p - pre - margin) & (others < p + post + margin))
                         for p in rd_ok])
    notes = []
    measure_pt = isolated.sum() >= MIN_CLEAN_BEATS
    use = rd_ok[isolated] if measure_pt else rd_ok
    if not measure_pt:
        notes.append("PR/QT not measured: different-shape beats fall next to most beats")

    beats = np.array([mv[p - pre:p + post] for p in use])
    beats -= np.median(beats[:, :int(0.05 * FS)], axis=1, keepdims=True)
    tpl = np.median(beats, axis=0)
    sign = np.sign(tpl[pre]) or 1.0
    s = tpl * sign
    noise = float(np.median(np.abs(beats - tpl)))

    on, off = _qrs_bounds(s, pre)
    tp = te = pp = pon = None
    if measure_pt:
        tp, te = _t_wave(s, off, int(rr_s * FS) if rr_s else int(0.8 * FS))
        pp, pon = _p_wave(s, on, noise)
        if te is None:
            notes.append("QT not measured: T wave end not identifiable")
    fid = Fiducials(pre, on, off, tp, te, pp, pon)

    if device_hr and rr_s and abs(60 / rr_s - device_hr) > HR_TOLERANCE:
        notes = ["Intervals withheld: beat classification uncertain (heart rate disagrees "
                 "with the device)"]
        return Analysis(mv, r, dom, tpl, Fiducials(pre, on, off), rr_s, {}, notes)

    ms = lambda a, b: (b - a) * 1000 / FS  # noqa: E731
    iv = {"QRS": ms(on, off)}
    if pon is not None:
        iv["PR"] = ms(pon, on)
    if te is not None:
        iv["QT"] = ms(on, te)
        if rr_s:
            iv["QTcB"] = iv["QT"] / np.sqrt(rr_s)
            iv["QTcF"] = iv["QT"] / np.cbrt(rr_s)
    return Analysis(mv, r, dom, tpl, fid, rr_s, iv, notes)
