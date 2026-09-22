"""Download recordings from an EMAY EMG-10 to CSV + PNG.

Usage:
  python download.py                 # sync clock, download every recording not already saved
  python download.py --list          # sync clock, list recordings only
  python download.py --record 1 3    # download specific recordings (1 = newest)
  python download.py --out DIR       # output directory (default: recordings/)
  python download.py --replot        # regenerate PNGs from saved CSVs (no device needed)
  python download.py --accept-disclaimer   # accept DISCLAIMER.md non-interactively (asked once)
"""
import argparse
import csv
import sys
from pathlib import Path

from acknowledge import require_acknowledgement
from ecg_analysis import analyze
from ecg_plot import render
from environment import summary as env_summary
from emg10 import (BASELINE, EMG10, SAMPLE_RATE_HZ, EMG10Error, RecordingInfo, finding_labels,
                   parse_header)


def stem(info: RecordingInfo) -> str:
    when = info.recorded_at.strftime("%Y%m%d_%H%M%S") if info.recorded_at else "nodate"
    return f"{when}_hr{info.heart_rate}"


def save_csv(path: Path, samples: list[int]):
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "raw", "centered"])
        for i, v in enumerate(samples):
            w.writerow([f"{i / SAMPLE_RATE_HZ:.3f}", v, v - BASELINE])


def save_png(path: Path, info: RecordingInfo, samples: list[int]):
    when = info.recorded_at.strftime("%Y-%m-%d %H:%M:%S") if info.recorded_at else "unknown date"
    render(path, analyze(samples), f"EMAY EMG-10 recording  -  {when}",
           device_hr=info.heart_rate, result_codes=info.result_codes)


def replot(out: Path):
    """Regenerate every PNG from saved CSVs (no device needed)."""
    with (out / "index.csv").open() as f:
        infos = {r["file_stem"]: parse_header(bytes.fromhex(r["raw_header"])) for r in csv.DictReader(f)}
    for stem_, info in sorted(infos.items()):
        src = out / f"{stem_}.csv"
        if not src.exists():
            continue
        with src.open() as f:
            samples = [int(r["raw"]) for r in csv.DictReader(f)]
        save_png(src.with_suffix(".png"), info, samples)
        print(f"  replotted {stem_}.png")


def write_index(out: Path, infos: list[RecordingInfo]):
    with (out / "index.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["index", "recorded_at", "heart_rate", "duration_s", "result_codes",
                    "file_stem", "raw_header", "software"])
        for i in infos:
            w.writerow([i.index, i.recorded_at.isoformat() if i.recorded_at else "",
                        i.heart_rate, i.duration_s, f"{i.result_codes[0]},{i.result_codes[1]}",
                        stem(i), i.raw_header.hex(" "), env_summary()])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--record", type=int, nargs="*")
    ap.add_argument("--out", type=Path, default=Path("recordings"))
    ap.add_argument("--force", action="store_true", help="re-download files that already exist")
    ap.add_argument("--replot", action="store_true", help="regenerate PNGs from saved CSVs; no device")
    ap.add_argument("--accept-disclaimer", action="store_true",
                    help="record acceptance of DISCLAIMER.md without the interactive prompt")
    args = ap.parse_args()
    require_acknowledgement(args.accept_disclaimer)
    print("NOTE: not a medical device. Output is informational only and not a diagnosis; "
          "see DISCLAIMER.md.", file=sys.stderr)
    if args.replot:
        replot(args.out)
        return

    def waiting():
        print("Waiting for EMG-10... turn it on / connect USB", file=sys.stderr)

    # The EMG-10 powers itself off after a few minutes even mid-transfer, so a full
    # download may take several sessions. Each pass skips files already saved.
    first = True
    forced = set()
    while True:
        try:
            if session(args, waiting, verbose=first, forced=forced):
                return
        except (OSError, EMG10Error) as e:
            print(f"\n  device disconnected ({e}); wake it to continue", file=sys.stderr)
        first = False


def session(args, waiting, verbose: bool, forced: set) -> bool:
    """One connection. Returns True when everything requested has been saved."""
    with EMG10.connect(wait_s=180, on_wait=waiting) as dev:
        dev.identify()
        dev.set_clock()
        infos = dev.list_recordings()
        if verbose:
            print(f"{len(infos)} recordings on device (clock synced)")
            for i in infos:
                when = i.recorded_at.isoformat(sep=" ") if i.recorded_at else "?"
                print(f"  {i.index:3d}  {when}  HR {i.heart_rate:3d}  {i.duration_s:4.0f}s  "
                      f"{' + '.join(finding_labels(i.result_codes))}")
        if args.list:
            return True

        args.out.mkdir(parents=True, exist_ok=True)
        write_index(args.out, infos)
        wanted = [i for i in infos if not args.record or i.index in args.record]
        for info in wanted:
            base = args.out / f"{stem(info)}"
            if base.with_suffix(".csv").exists() and (not args.force or base in forced):
                continue
            samples = dev.download(
                info, progress=lambda k, n: print(f"\r  #{info.index}: {k}/{n}", end="", file=sys.stderr))
            print(file=sys.stderr)
            save_csv(base.with_suffix(".csv"), samples)
            save_png(base.with_suffix(".png"), info, samples)
            forced.add(base)
            print(f"  saved {base.name}.csv/.png")
        return True


if __name__ == "__main__":
    main()
