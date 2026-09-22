"""Send one command to the EMAY EMG-10 and log any replies.

Usage: python tools/hid_probe.py <hex bytes> [--len N] [--wait S]
  e.g. python tools/hid_probe.py "81 01" --len 65
The payload is prefixed with report ID 0x00 and zero-padded to --len bytes total.
"""
import argparse
import time

import hid

VID, PID = 0x4444, 0x5555


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("payload")
    ap.add_argument("--len", type=int, default=65)
    ap.add_argument("--wait", type=float, default=3.0)
    args = ap.parse_args()

    body = bytes.fromhex(args.payload)
    pkt = (b"\x00" + body).ljust(args.len, b"\x00")

    dev = hid.device()
    dev.open(VID, PID)
    n = dev.write(pkt)
    print(f"W {n}/{len(pkt)}: {pkt[:16].hex(' ')} ...")
    t0 = time.monotonic()
    got = 0
    while time.monotonic() - t0 < args.wait:
        data = dev.read(64, timeout_ms=200)
        if data:
            got += 1
            print(f"R {time.monotonic() - t0:6.3f} {len(data)}: {bytes(data).hex(' ')}")
    print(f"# {got} replies")
    dev.close()


if __name__ == "__main__":
    main()
