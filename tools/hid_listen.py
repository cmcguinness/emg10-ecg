"""Passively log raw HID input reports from the EMAY EMG-10 (read-only, sends nothing).

Usage: python tools/hid_listen.py [seconds] [outfile]
"""
import sys
import time

import hid

VID, PID = 0x4444, 0x5555


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30
    out = open(sys.argv[2], "w") if len(sys.argv) > 2 else sys.stdout

    dev = hid.device()
    dev.open(VID, PID)
    dev.set_nonblocking(False)
    print(f"# opened {dev.get_manufacturer_string()} {dev.get_product_string()}; "
          f"listening {seconds}s", file=out, flush=True)

    t0 = time.monotonic()
    n = 0
    while (elapsed := time.monotonic() - t0) < seconds:
        try:
            data = dev.read(64, timeout_ms=500)
        except OSError as e:  # device unplugged / powered off
            print(f"{elapsed:8.3f} ERROR {e}", file=out, flush=True)
            break
        if data:
            n += 1
            print(f"{elapsed:8.3f} {len(data):3d} {bytes(data).hex(' ')}", file=out, flush=True)
    print(f"# done: {n} reports", file=out, flush=True)
    dev.close()


if __name__ == "__main__":
    main()
