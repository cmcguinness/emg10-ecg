"""Render an EMG-10 recording as an ECG-paper style PNG with a labelled median beat."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ecg_analysis import FS, Analysis  # noqa: E402

MM = 1 / 25.4                 # inches per mm
PAPER_SPEED = 25              # mm/s for the rhythm strips
BEAT_SPEED = 100              # mm/s for the enlarged median beat
STRIP_S = 10
MINOR, MAJOR, TRACE = "#f6c9c9", "#e58f8f", "#1a1a1a"
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
    summary_h = (12 + len(a.notes)) * 5 + 12     # summary lines + disclaimer, mm
    fig_h = header + n_strips * (strip_h + gap) + max(beat_h, summary_h) + gap + margin
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
        m = (t >= x0) & (t < x1)
        ax.plot(t[m], a.mv[m], color=TRACE, lw=0.6)
        for p, d in zip(a.r_peaks, a.dominant):
            if x0 <= p / FS < x1:
                ax.plot(p / FS, hi_mv - 0.07 * (hi_mv - lo_mv), marker="v" if d else "D", ms=2.5 if d else 3,
                        color="#2060c0" if d else "#d07000", ls="none")
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
        ax.set_title(f"Median of {int(a.dominant.sum())} dominant beats  ({BEAT_SPEED} mm/s, {beat_gain} mm/mV)",
                     fontsize=7, loc="left")

    iv = a.intervals_ms
    hr_txt = f"{hr:.0f} bpm" if hr else "n/a"
    if device_hr:
        hr_txt += f"   (device: {device_hr} bpm)"
    lines = [
        ("Heart rate", hr_txt),
        ("RR (median)", _fmt(a.rr_s * 1000 if a.rr_s else None)),
        ("PR", _fmt(iv.get("PR")) if "PR" in iv else
         ("n/a - see note" if a.notes else "n/a - P wave not detectable")),
        ("QRS", _fmt(iv.get("QRS"))),
        ("QT", _fmt(iv.get("QT"))),
        ("QTc Bazett", _fmt(iv.get("QTcB"))),
        ("QTc Fridericia", _fmt(iv.get("QTcF"))),
        ("Beats", f"{len(a.r_peaks)} detected, {a.n_other} with a different shape (orange, not measured)"),
    ]
    if result_codes:
        lines.append(("Device result codes", f"{result_codes[0]}, {result_codes[1]}"))
    for n in a.notes:
        lines.append(("Note", n))
    sx = (margin + beat_w + 10) / fig_w
    for k, (label, val) in enumerate(lines):
        yy = 1 - (by + 6 + k * 5) / fig_h
        fig.text(sx, yy, label, fontsize=7.5, color="0.35", va="center")
        fig.text(sx + 34 / fig_w, yy, val, fontsize=7.5, va="center")
    fig.text(sx, 1 - (by + 8 + len(lines) * 5) / fig_h,
             "Automated estimates from a single-lead handheld device; not a diagnosis.\n"
             "Amplitude: 500 counts/mV, calibrated against the Contec app display.",
             fontsize=6, color="0.45", va="top", style="italic")

    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)
