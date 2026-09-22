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
COUNTS_PER_MV = 500    # calibrated against the Contec app display at 10 mm/mV (R and S waves agree within 5%)
PRE_S, POST_S = 0.35, 0.60   # median-beat window around R
MIN_CLEAN_BEATS = 5          # beats with no different-shape neighbour needed to measure P and T
QT_PLAUSIBLE_MS = (260, 600)  # outside this, the T wave was almost certainly misidentified


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
    dominant: np.ndarray                # bool mask over r_peaks: reference-shape beats
    template: np.ndarray | None         # median dominant beat, mV
    fid: Fiducials | None
    rr_s: float | None                  # median RR between consecutive reference beats (for QTc)
    intervals_ms: dict = field(default_factory=dict)   # PR, QRS, QT, QTcB, QTcF
    notes: list[str] = field(default_factory=list)     # why a measurement was skipped
    one_off: np.ndarray | None = None   # bool mask over r_peaks: other-shape beats whose shape occurs once
    busy: list[tuple[float, float]] = field(default_factory=list)  # high-activity windows, seconds
    rr_cv: float | None = None          # coefficient of variation of consecutive main-beat RR, %
    rr_rmssd_ms: float | None = None    # RMS of successive RR differences (main beats), ms

    @staticmethod
    def _rate(beats: np.ndarray) -> float | None:
        if len(beats) < 2 or beats[-1] == beats[0]:
            return None
        return (len(beats) - 1) * 60 * FS / (beats[-1] - beats[0])

    @property
    def heart_rate(self) -> float | None:
        """Beats per minute, counting reference and recurring other-shape beats. One-off
        shapes are left out: from a single example they may be artifacts."""
        return self._rate(self.r_peaks[~self.one_off_mask])

    @property
    def reference_rate(self) -> float | None:
        """Reference-shape beats per minute."""
        return self._rate(self.r_peaks[self.dominant])

    @property
    def one_off_mask(self) -> np.ndarray:
        return self.one_off if self.one_off is not None else np.zeros(len(self.r_peaks), bool)

    @property
    def n_other(self) -> int:
        """Other-shape beats whose shape recurs (orange)."""
        return int((~self.dominant & ~self.one_off_mask).sum())

    @property
    def n_one_off(self) -> int:
        """Other-shape beats whose shape occurs only once (grey)."""
        return int(self.one_off_mask.sum())


def to_mv(raw_counts) -> np.ndarray:
    return (np.asarray(raw_counts, float) - 8192) / COUNTS_PER_MV


def detect_beats(mv: np.ndarray, clean: np.ndarray) -> np.ndarray:
    """Beat locations: NeuroKit2's energy-based detector (finds either polarity), each
    detection moved to the largest raw deflection within +-150 ms, since detections of
    wide beats often land on their trailing upswing. Detections < 200 ms apart merge."""
    r0 = np.asarray(nk.ecg_peaks(clean, sampling_rate=FS, method="elgendi2010")[1]["ECG_R_Peaks"])
    w = int(0.15 * FS)
    ks = sorted({max(p - w, 0) + int(np.argmax(np.abs(mv[max(p - w, 0):p + w]))) for p in r0})
    out: list[int] = []
    for k in ks:
        if out and k - out[-1] < int(0.2 * FS):
            if abs(mv[k]) > abs(mv[out[-1]]):
                out[-1] = k
        else:
            out.append(k)
    return np.array(out, dtype=int)


def qrs_width_ms(mv: np.ndarray, k: int) -> float:
    """Width of the main deflection at 30% of its peak."""
    a = mv[k]
    sign, th = (np.sign(a) or 1.0), 0.3 * abs(a)
    lo = hi = k
    while lo > 0 and mv[lo - 1] * sign > th:
        lo -= 1
    while hi < len(mv) - 1 and mv[hi + 1] * sign > th:
        hi += 1
    return (hi - lo + 1) * 1000 / FS


def _similar(mv, k, ref_k, width, ref_width, w) -> bool:
    if np.sign(mv[k]) != np.sign(mv[ref_k]):
        return False
    if not (0.5 <= abs(mv[k]) / abs(mv[ref_k]) <= 2.0):
        return False
    if not (1 / 1.5 <= width / ref_width <= 1.5):
        return False
    a, b = mv[k - w:k + w], mv[ref_k - w:ref_k + w]
    if a.std() == 0 or b.std() == 0:
        return True
    return float(np.corrcoef(a, b)[0, 1]) >= 0.5


def classify(mv: np.ndarray, r: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Group beats by shape (polarity, amplitude within 2x, width within 1.5x, loose
    correlation) and return a mask of the reference group: the narrowest group holding at
    least 20% of beats. Also returns a mask of beats whose shape occurs only once.
    This describes shape only; it is not a clinical classification."""
    w = int(0.06 * FS)
    ok = np.flatnonzero((r >= w) & (r < len(mv) - w))
    ref = np.zeros(len(r), bool)
    one_off = np.zeros(len(r), bool)
    if len(ok) < 3:
        ref[ok] = True
        return ref, one_off
    widths = {i: qrs_width_ms(mv, r[i]) for i in ok}
    # seed groups from the largest deflections first so each group's exemplar is a clear beat
    groups: list[list[int]] = []
    for i in sorted(ok, key=lambda i: -abs(mv[r[i]])):
        for g in groups:
            if _similar(mv, r[i], r[g[0]], widths[i], widths[g[0]], w):
                g.append(i)
                break
        else:
            groups.append([i])
    big = [g for g in groups if len(g) >= max(3, 0.2 * len(ok))] or [max(groups, key=len)]
    best = min(big, key=lambda g: (np.median([widths[i] for i in g]), -len(g)))
    ref[best] = True
    for g in groups:
        if len(g) == 1 and g is not best:
            one_off[g[0]] = True
    return ref, one_off


def _drop_t_wave_detections(mv, r, ref, one_off):
    """Remove non-reference detections with the reference beats' polarity, under 45% of their
    height, within 450 ms after a reference beat: almost always a T wave, not a beat.
    (Opposite-polarity deflections are kept; they are usually real wide beats.)"""
    if ref.sum() < 3:
        return r, ref, one_off
    ref_amp = np.median(np.abs(mv[r[ref]]))
    ref_sign = np.sign(np.median(mv[r[ref]]))
    keep = np.ones(len(r), bool)
    ref_pos = r[ref]
    for i in np.flatnonzero(~ref):
        prev = ref_pos[ref_pos < r[i]]
        if (len(prev) and r[i] - prev[-1] <= int(0.45 * FS) and np.sign(mv[r[i]]) == ref_sign
                and abs(mv[r[i]]) < 0.45 * ref_amp):
            keep[i] = False
    return r[keep], ref[keep], one_off[keep]


BUSY_WINDOW_S = 2.0
BUSY_THRESHOLD = 0.045   # ~99th percentile of between-beat activity across the downloaded recordings


def rhythm_variation(r: np.ndarray, ref: np.ndarray) -> tuple[float | None, float | None]:
    """Beat-to-beat variation of the main rhythm, using only runs of consecutive reference
    beats so other-shape beats do not inflate it. Returns (CV %, RMSSD ms)."""
    rr, diffs = [], []
    for i in range(len(r) - 1):
        if ref[i] and ref[i + 1]:
            rr.append((r[i + 1] - r[i]) * 1000 / FS)
            if i + 2 < len(r) and ref[i + 2]:
                diffs.append((r[i + 2] - r[i + 1] - (r[i + 1] - r[i])) * 1000 / FS)
    if len(rr) < 5:
        return None, None
    cv = float(np.std(rr) / np.mean(rr) * 100)
    rmssd = float(np.sqrt(np.mean(np.square(diffs)))) if len(diffs) >= 4 else None
    return cv, rmssd


def busy_windows(mv: np.ndarray, r: np.ndarray, ref: np.ndarray) -> list[tuple[float, float]]:
    """Windows with unusually high between-beat activity: mean |sample-to-sample change|
    outside the QRS complexes, relative to the reference beats' height. Could be noise or
    contact trouble, or a run of unusual beats, so they are flagged, never excluded."""
    ref_amp = np.median(np.abs(mv[r[ref]])) if ref.any() else np.percentile(np.abs(mv), 99)
    if ref_amp <= 0:
        return []
    mask = np.ones(len(mv), bool)
    half = int(0.08 * FS)
    for k in r:
        mask[max(k - half, 0):k + half] = False
    d = np.abs(np.diff(mv, prepend=mv[0]))
    w = int(BUSY_WINDOW_S * FS)
    out: list[tuple[float, float]] = []
    for start in range(0, len(mv) - w + 1, w):
        m = mask[start:start + w]
        if m.sum() > 50 and d[start:start + w][m].mean() / ref_amp > BUSY_THRESHOLD:
            a, b = start / FS, (start + w) / FS
            if out and out[-1][1] == a:
                out[-1] = (out[-1][0], b)
            else:
                out.append((a, b))
    return out


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
    k = int(0.04 * FS)
    sm = np.convolve(s, np.ones(k) / k, mode="same")
    seg = sm[start:stop]
    tp = start + int(np.argmax(np.abs(seg)))
    amp = sm[tp]
    if abs(amp) < 0.15 * np.max(np.abs(s)):
        return None, None
    # tangent method on the trailing limb (of the smoothed wave)
    slope = np.diff(sm[tp:stop + 1]) * np.sign(amp)
    if len(slope) < 2 or slope.min() >= 0:
        return tp, None
    k = int(np.argmin(slope))
    x0, y0, m = tp + k, sm[tp + k], sm[tp + k + 1] - sm[tp + k]
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


def analyze(raw_counts) -> Analysis:
    mv = to_mv(raw_counts)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        clean = nk.ecg_clean(mv, sampling_rate=FS)
    r = detect_beats(mv, clean)
    if len(r) < 3:
        return Analysis(mv, r, np.ones(len(r), bool), None, None, None)
    dom, one_off = classify(mv, r)
    r, dom, one_off = _drop_t_wave_detections(mv, r, dom, one_off)
    busy = busy_windows(mv, r, dom)
    pre, post = int(PRE_S * FS), int(POST_S * FS)
    rd = r[dom]
    rd_ok = rd[(rd >= pre) & (rd < len(mv) - post)]
    # RR only between consecutive beats that are both dominant
    rr = [b - a for a, b, da, db in zip(r, r[1:], dom, dom[1:]) if da and db]
    rr_s = float(np.median(rr)) / FS if rr else None
    rr_cv, rr_rmssd = rhythm_variation(r, dom)
    if len(rd_ok) < 3:
        return Analysis(mv, r, dom, None, None, rr_s, one_off=one_off, busy=busy, rr_cv=rr_cv,
                        rr_rmssd_ms=rr_rmssd)

    # P and T are only measurable on beats with no different-shape beat nearby; otherwise
    # the median beat mixes in the neighbouring complex.
    margin = int(0.1 * FS)   # allow for the width of a neighbouring wide beat
    others = r[~dom]
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
        if te is not None and not (QT_PLAUSIBLE_MS[0] <= (te - on) * 1000 / FS <= QT_PLAUSIBLE_MS[1]):
            tp = te = None
            notes.append("QT not measured: T wave ambiguous")
        elif te is None:
            notes.append("QT not measured: T wave end not identifiable")
    fid = Fiducials(pre, on, off, tp, te, pp, pon)

    ms = lambda a, b: (b - a) * 1000 / FS  # noqa: E731
    iv = {"QRS": ms(on, off)}
    if pon is not None:
        iv["PR"] = ms(pon, on)
    if te is not None:
        iv["QT"] = ms(on, te)
        if rr_s:
            iv["QTcB"] = iv["QT"] / np.sqrt(rr_s)
            iv["QTcF"] = iv["QT"] / np.cbrt(rr_s)
    return Analysis(mv, r, dom, tpl, fid, rr_s, iv, notes, one_off, busy, rr_cv, rr_rmssd)
