"""USB HID protocol for the EMAY EMG-10 handheld ECG (a rebadged Contec PM10).

Reverse-engineered from the Contec "Portable ECG Monitor" macOS app (see STATUS.md).
Every report is 64 bytes. Commands/replies have the high bit set; data bytes are 7-bit,
and multi-byte numbers are big-endian groups of 7 bits (e.g. year 2026 = 0f 6a).

    81            -> f1 ...                identify
    82 Y Y M D h m s -> f2 (echo)          set clock
    90            -> e0 n                  number of stored recordings
    fe            -> e1 ...                next recording header (repeat n times)
    a0 lo hi      -> d0 ... x N            download recording (1 = newest)
    a0 7f 7f                               end session

This module only ever sends the commands above. It never writes settings (0x83 with
arguments) and never sends unknown commands.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

import hid

VID, PID = 0x4444, 0x5555
REPORT_LEN = 64
SAMPLE_RATE_HZ = 250          # 7500 samples per 30 s recording
BASELINE = 8192               # 14-bit midpoint; raw value for 0 mV
SAMPLES_PER_PACKET = 25
DATA_OFFSET = 11              # first sample byte in a d0 packet


# The device's own screening findings, stored as up to two codes per recording (header
# bytes 16-17). Labels from the Contec app's Feature.plist.
DEVICE_FINDINGS = {
    0: "No abnormal", 1: "Missed Beat", 2: "Accidental VPB", 3: "VPB Trigeminy",
    4: "VPB Bigeminy", 5: "VPB Couple", 6: "VPB runs of 3", 7: "VPB runs of 4",
    8: "VPB RonT", 9: "Bradycardia", 10: "Tachycardia", 11: "Arrhythmia",
    12: "ST Elevation", 13: "ST Depression",
}


def finding_labels(codes: tuple[int, int]) -> list[str]:
    """Device finding labels for a recording's result codes (0 in the second slot = none)."""
    first, second = codes
    labels = [DEVICE_FINDINGS.get(first, f"Unknown code {first}")]
    if second:
        labels.append(DEVICE_FINDINGS.get(second, f"Unknown code {second}"))
    return labels


class EMG10Error(RuntimeError):
    pass


class DeviceNotFound(EMG10Error):
    """The device never appeared within the wait period."""


def _u7(*parts: int) -> int:
    """Combine 7-bit groups, most significant first."""
    v = 0
    for p in parts:
        v = (v << 7) | (p & 0x7F)
    return v


def _split7(v: int, n: int) -> list[int]:
    return [(v >> (7 * i)) & 0x7F for i in reversed(range(n))]


@dataclass
class RecordingInfo:
    index: int                  # 1 = newest
    recorded_at: datetime | None
    n_samples: int
    heart_rate: int
    result_codes: tuple[int, int]
    raw_header: bytes

    @property
    def duration_s(self) -> float:
        return self.n_samples / SAMPLE_RATE_HZ


def parse_header(b: bytes) -> RecordingInfo:
    try:
        when = datetime(_u7(b[3], b[4]), b[5], b[6], b[7], b[8], b[9])
    except ValueError:
        when = None
    return RecordingInfo(
        index=_u7(b[2], b[1]),
        recorded_at=when,
        n_samples=_u7(b[10], b[11], b[12], b[13]),
        heart_rate=_u7(b[14], b[15]),
        result_codes=(b[16], b[17]),
        raw_header=bytes(b[:24]),
    )


def parse_samples(packet: bytes) -> list[int]:
    end = DATA_OFFSET + 2 * SAMPLES_PER_PACKET
    return [_u7(packet[i], packet[i + 1]) for i in range(DATA_OFFSET, end, 2)]


class EMG10:
    def __init__(self, dev: hid.device):
        self._dev = dev

    # --- connection -------------------------------------------------------
    @classmethod
    def connect(cls, wait_s: float = 60, on_wait=None) -> "EMG10":
        """Open the device, waiting up to wait_s for it to be switched on."""
        deadline = time.monotonic() + wait_s
        announced = False
        while True:
            if hid.enumerate(VID, PID):
                time.sleep(1.0)  # device ignores commands for ~1 s after enumerating
                dev = hid.device()
                try:
                    dev.open(VID, PID)
                    return cls(dev)
                except OSError:
                    pass
            if time.monotonic() > deadline:
                raise DeviceNotFound("EMG-10 not found; turn it on and connect the USB cable")
            if on_wait and not announced:
                on_wait()
                announced = True
            time.sleep(0.5)

    def close(self):
        try:
            self._send(0xA0, 0x7F, 0x7F)
        except (OSError, EMG10Error):
            pass  # device already gone (it powers off on its own)
        self._dev.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- low level ----------------------------------------------------------
    def _send(self, *payload: int):
        pkt = bytes([0x00, *payload]).ljust(REPORT_LEN + 1, b"\x00")  # report ID 0
        if self._dev.write(pkt) < 0:
            raise EMG10Error("HID write failed")

    def _drain(self):
        while self._dev.read(REPORT_LEN, timeout_ms=5):
            pass

    def _expect(self, reply: int, timeout_s: float = 2.0) -> bytes:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            data = self._dev.read(REPORT_LEN, timeout_ms=100)
            if data and data[0] == reply:
                return bytes(data)
        raise EMG10Error(f"timed out waiting for reply 0x{reply:02x}")

    def _command(self, *payload: int, reply: int, timeout_s: float = 2.0) -> bytes:
        self._drain()
        self._send(*payload)
        return self._expect(reply, timeout_s)

    # --- protocol -----------------------------------------------------------
    def identify(self) -> bytes:
        return self._command(0x81, reply=0xF1)

    def set_clock(self, when: datetime | None = None):
        when = when or datetime.now()
        self._command(0x82, *_split7(when.year, 2), when.month, when.day,
                      when.hour, when.minute, when.second, reply=0xF2)

    def count(self) -> int:
        b = self._command(0x90, reply=0xE0)
        return _u7(b[2], b[1])

    def list_recordings(self) -> list[RecordingInfo]:
        n = self.count()
        return [parse_header(self._command(0xFE, reply=0xE1)) for _ in range(n)]

    def download(self, info: RecordingInfo, progress=None) -> list[int]:
        n_packets = -(-info.n_samples // SAMPLES_PER_PACKET)
        lo, hi = _split7(info.index, 2)[::-1]
        self._drain()
        self._send(0xA0, lo, hi)
        samples: list[int] = []
        for i in range(n_packets):
            samples.extend(parse_samples(self._expect(0xD0, timeout_s=3.0)))
            if progress:
                progress(i + 1, n_packets)
        return samples[: info.n_samples]
