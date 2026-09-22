"""Render an EMG-10 recording as an ECG-paper style PNG with a labelled median beat."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import textwrap  # noqa: E402

from ecg_analysis import FS, Analysis  # noqa: E402
from ecg_explain import explain, typical, variation_label  # noqa: E402
from emg10 import finding_labels  # noqa: E402

MM = 1 / 25.4                 # inches per mm
PAPER_SPEED = 25              # mm/s for the rhythm strips
BEAT_SPEED = 100              # mm/s for the enlarged median beat
STRIP_S = 10
MINOR, MAJOR, TRACE = "#f6c9c9", "#e58f8f", "#1a1a1a"
REF_C, OTHER_C, ONE_OFF_C, BUSY_C = "#2060c0", "#d07000", "#8a8a8a", "#fff2b3"
LINE_MM = 3.4                 # explanation text line height
GAINS = (10, 20, 40, 80, 160)  # mm/mV; pick the smallest that makes R >= ~8 mm


def pick_gain(a: Analysis) -> int:
    peak = np.percentile(np.abs(a.mv), 99.5) if len(a.mv) else 1
    for g in GAINS:
        if peak * g >= 8:
            return g
    return GAINS[-1]


def _paper(ax, x0, x1, y0, y1, speed, gain):
    """Draw 1 mm / 5 mm grid in data units (seconds, mV) and lock the aspect to true mm."""
    for step, color, lw in ((1, MINOR, 0.4), (5, MAJOR, 0.8)):
        dx, dy = step / speed, step / gain
        for x in np.arange(np.floor(x0 / dx) * dx, x1 + 1e-9, dx):
            ax.axvline(x, color=color, lw=lw, zorder=0)
        for y in np.arange(np.floor(y0 / dy) * dy, y1 + 1e-9, dy):
            ax.axhline(y, color=color, lw=lw, zorder=0)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect(gain / speed)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)


def _cal_pulse(ax, x, y0, gain, height_mv):
    w = 0.2
    ax.plot([x, x + 0.04, x + 0.04, x + 0.04 + w, x + 0.04 + w, x + 0.08 + w],
            [y0, y0, y0 + height_mv, y0 + height_mv, y0, y0], color=TRACE, lw=1)
    ax.text(x + 0.04 + w / 2, y0 + height_mv, f"{height_mv:g} mV", ha="center", va="bottom", fontsize=6)


def _nice_cal(gain):
    """Largest round calibration amplitude that draws no taller than 10 mm."""
    for mv in (1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01):
        if mv * gain <= 10:
            return mv
    return 0.01


def _fmt(v, unit="ms"):
    return f"{v:.0f} {unit}" if v is not None else "n/a"


def render(path, a: Analysis, title: str, device_hr: int | None = None,
           result_codes: tuple[int, int] | None = None):
    gain = pick_gain(a)
    lo_mv = min(np.percentile(a.mv, 0.05), -2 / gain) if len(a.mv) else -1
    hi_mv = max(np.percentile(a.mv, 99.95), 2 / gain) if len(a.mv) else 1
    pad = 0.15 * (hi_mv - lo_mv)
    lo_mv, hi_mv = lo_mv - pad, hi_mv + 1.6 * pad    # headroom for beat markers
    strip_h = (hi_mv - lo_mv) * gain       # mm
    n_strips = max(1, int(np.ceil(len(a.mv) / FS / STRIP_S)))
    strip_w = STRIP_S * PAPER_SPEED        # 250 mm

    beat_s = len(a.template) / FS if a.template is not None else 0.95
    beat_w = beat_s * BEAT_SPEED
    beat_half = (np.max(np.abs(a.template)) * 1.3) if a.template is not None else hi_mv
    beat_gain = gain * 2
    beat_h = 2 * beat_half * beat_gain

    margin, header, gap = 12, 22, 6
    fig_w = strip_w + 2 * margin
    summary_h = (13 + len(a.notes)) * 5 + 16     # summary lines + disclaimer, mm
    expl = [(h, textwrap.wrap(t, 145)) for h, t in explain(a, device_hr, result_codes)]
    expl_h = 10 + sum(len(lines) * LINE_MM + 1.5 for _, lines in expl)
    fig_h = header + n_strips * (strip_h + gap) + max(beat_h, summary_h) + gap + expl_h + margin
    fig = plt.figure(figsize=(fig_w * MM, fig_h * MM), dpi=150)
    fig.patch.set_facecolor("white")

    def axes_at(x_mm, y_top_mm, w_mm, h_mm):
        return fig.add_axes([x_mm / fig_w, 1 - (y_top_mm + h_mm) / fig_h, w_mm / fig_w, h_mm / fig_h])

    # header
    hr = a.heart_rate
    fig.text(margin / fig_w, 1 - 7 / fig_h, title, fontsize=10, weight="bold", va="center")
    fig.text(margin / fig_w, 1 - 14 / fig_h,
             f"Lead I  |  {PAPER_SPEED} mm/s  |  {gain} mm/mV ({gain // 10}x standard gain)  |  "
             f"{FS} Hz  |  device band 1-20 Hz", fontsize=7, va="center", color="0.3")

    # rhythm strips
    t = np.arange(len(a.mv)) / FS
    y = 0
    for i in range(n_strips):
        ax = axes_at(margin, header + i * (strip_h + gap), strip_w, strip_h)
        x0, x1 = i * STRIP_S, (i + 1) * STRIP_S
        _paper(ax, x0, x1, lo_mv, hi_mv, PAPER_SPEED, gain)
        for b0, b1 in a.busy:
            if b1 > x0 and b0 < x1:
                ax.axvspan(max(b0, x0), min(b1, x1), color=BUSY_C, alpha=0.55, zorder=0.5, lw=0)
                ax.text(max(b0, x0) + 0.05, lo_mv + 0.12 * (hi_mv - lo_mv), "check", fontsize=5.5,
                        color="#8a6d00", style="italic")
        m = (t >= x0) & (t < x1)
        ax.plot(t[m], a.mv[m], color=TRACE, lw=0.6)
        for p, d, o in zip(a.r_peaks, a.dominant, a.one_off_mask):
            if x0 <= p / FS < x1:
                style = ("v", 2.5, REF_C) if d else (("o", 2.5, ONE_OFF_C) if o else ("D", 3, OTHER_C))
                ax.plot(p / FS, hi_mv - 0.07 * (hi_mv - lo_mv), marker=style[0], ms=style[1],
                        color=style[2], ls="none")
        ax.text(x0 + 0.05, lo_mv + 0.04 * (hi_mv - lo_mv), f"{x0}s", fontsize=6, color="0.35")
        if i == 0:
            _cal_pulse(ax, x0 + 0.1, lo_mv + 0.2 * (hi_mv - lo_mv), gain, _nice_cal(gain))
        y = header + (i + 1) * (strip_h + gap)

    # median beat panel + summary
    by = y
    if a.template is not None and a.fid is not None:
        f = a.fid
        tb = (np.arange(len(a.template)) - f.r) / FS
        ax = axes_at(margin, by, beat_w, beat_h)
        _paper(ax, tb[0], tb[-1], -beat_half, beat_half, BEAT_SPEED, beat_gain)
        ax.plot(tb, a.template, color=TRACE, lw=1.1)
        tt = lambda i: (i - f.r) / FS  # noqa: E731
        for name, idx in (("P", f.p_peak), ("R", f.r), ("T", f.t_peak)):
            if idx is not None:
                ax.annotate(name, (tt(idx), a.template[idx]), xytext=(0, 6 if a.template[idx] >= 0 else -10),
                            textcoords="offset points", ha="center", fontsize=8, weight="bold", color="#2060c0")
        for name, lo_i, hi_i, lvl in (("PR", f.p_on, f.qrs_on, -0.55), ("QRS", f.qrs_on, f.qrs_off, -0.72),
                                      ("QT", f.qrs_on, f.t_end, -0.9)):
            if lo_i is None or hi_i is None or name not in a.intervals_ms:
                continue
            yl = beat_half * lvl
            ax.annotate("", (tt(lo_i), yl), (tt(hi_i), yl),
                        arrowprops=dict(arrowstyle="<->", color="#c03030", lw=0.8, shrinkA=0, shrinkB=0))
            ax.text((tt(lo_i) + tt(hi_i)) / 2, yl, f"{name} {(hi_i - lo_i) * 1000 / FS:.0f}",
                    ha="center", va="bottom", fontsize=6.5, color="#c03030")
            for xi in (lo_i, hi_i):
                ax.axvline(tt(xi), color="#c03030", lw=0.5, ls=":")
        ax.set_title(f"Median reference beat  ({BEAT_SPEED} mm/s, {beat_gain} mm/mV)",
                     fontsize=7, loc="left")

    iv = a.intervals_ms
    ref_hr = a.reference_rate
    hr_txt = f"{hr:.0f} bpm" if hr else "n/a"
    if device_hr:
        hr_txt += f"   (device: {device_hr} bpm)"
    lines = [
        ("Heart rate", hr_txt),
        ("Reference beats", (f"{ref_hr:.0f} per min" if ref_hr else "n/a")
         + (f"   ({a.n_other} other-shape beats)" if a.n_other else "   (all beats alike)")),
        ("RR (median)", _fmt(a.rr_s * 1000 if a.rr_s else None)),
        ("PR", _fmt(iv.get("PR")) if "PR" in iv else
         ("n/a - see note" if a.notes else "n/a - P wave not detectable")),
        ("QRS", _fmt(iv.get("QRS"))),
        ("QT", _fmt(iv.get("QT"))),
        ("QTc Bazett", _fmt(iv.get("QTcB"))),
        ("QTc Fridericia", _fmt(iv.get("QTcF"))),
        ("Beats", f"{len(a.r_peaks)} detected: {int(a.dominant.sum())} reference (blue), "
                  f"{a.n_other} other shape (orange), {a.n_one_off} one-off (grey)"),
    ]
    if a.busy:
        lines.append(("Check sections", ", ".join(f"{b0:.0f}-{b1:.0f} s" for b0, b1 in a.busy)
                      + " (shaded: high activity)"))
    if a.rr_cv is not None:
        lines.insert(3, ("Rhythm variation", f"{a.rr_cv:.1f}% ({variation_label(a.rr_cv)})"
                         + (f", RMSSD {a.rr_rmssd_ms:.0f} ms" if a.rr_rmssd_ms is not None else "")))
    if result_codes:
        lines.append(("Device finding", " + ".join(finding_labels(result_codes))
                      + f"   (codes {result_codes[0]}, {result_codes[1]})"))
    for n in a.notes:
        lines.append(("Note", n))
    sx = (margin + beat_w + 10) / fig_w
    typ = typical(a)
    typ_key = {"Heart rate": "HR", "PR": "PR", "QRS": "QRS", "QT": "QT", "QTc Bazett": "QTc",
               "QTc Fridericia": "QTc"}
    fig.text(sx + 80 / fig_w, 1 - (by + 1) / fig_h, "Typical (adult, resting)", fontsize=6.5,
             color="0.45", va="center", style="italic")
    for k, (label, val) in enumerate(lines):
        yy = 1 - (by + 6 + k * 5) / fig_h
        fig.text(sx, yy, label, fontsize=7.5, color="0.35", va="center")
        fig.text(sx + 34 / fig_w, yy, val, fontsize=7.5, va="center")
        if label in typ_key and typ_key[label] in typ:
            fig.text(sx + 80 / fig_w, yy, typ[typ_key[label]], fontsize=7, color="0.45", va="center")
    fig.text(sx, 1 - (by + 8 + len(lines) * 5) / fig_h,
             "Consumer handheld device + unvalidated software: estimates only, not a diagnosis.\n"
             "See 'Accuracy' below. Amplitude: 500 counts/mV (calibrated against the Contec app).",
             fontsize=6, color="0.45", va="top", style="italic")

    # plain-language explanations, full width
    ey = by + max(beat_h, summary_h) + gap
    fig.text(margin / fig_w, 1 - ey / fig_h, "What these measurements mean",
             fontsize=8.5, weight="bold", va="top")
    ey += 7
    for head, wrapped in expl:
        fig.text(margin / fig_w, 1 - ey / fig_h, head, fontsize=6.8, weight="bold", va="top", color="0.2")
        for j, line in enumerate(wrapped):
            fig.text((margin + 36) / fig_w, 1 - (ey + j * LINE_MM) / fig_h, line, fontsize=6.8, va="top")
        ey += len(wrapped) * LINE_MM + 1.5

    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)
