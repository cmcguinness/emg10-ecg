"""lldb script: log HID traffic of the Contec "Portable ECG Monitor" app (x86_64, Rosetta).

Usage:
  lldb -p <pid> -o "command script import tools/lldb_capture.py" -o "capture <logfile>" -o continue

Breakpoints (both auto-continue):
  IOHIDDeviceSetReport(dev, type, reportID, report, len)  -> rcx = report, r8 = len
  app input callback (ctx, result, sender, type, id, report, len) -> r9 = report, [rsp+8] = len
"""
import time

import lldb

CALLBACK_FILE_ADDR = 0x100003E76  # passed to IOHIDDeviceRegisterInputReportCallback
LOG = None


def _reg(frame, name):
    return frame.FindRegister(name).GetValueAsUnsigned()


def _dump(frame, tag, ptr, n):
    err = lldb.SBError()
    data = frame.GetThread().GetProcess().ReadMemory(ptr, n, err) if n else b""
    hexs = data.hex(" ") if err.Success() else f"<read error {err}>"
    LOG.write(f"{time.time():.3f} {tag} {n} {hexs}\n")
    LOG.flush()


def on_write(frame, bp_loc, extra_args, internal_dict):
    _dump(frame, "W", _reg(frame, "rcx"), _reg(frame, "r8"))
    return False  # don't stop


def on_read(frame, bp_loc, extra_args, internal_dict):
    rsp = _reg(frame, "rsp")
    err = lldb.SBError()
    n = frame.GetThread().GetProcess().ReadUnsignedFromMemory(rsp + 8, 8, err)
    _dump(frame, "R", _reg(frame, "r9"), n if err.Success() else 64)
    return False


def capture(debugger, command, result, internal_dict):
    global LOG
    LOG = open(command.strip() or "/tmp/contec_capture.log", "a")
    target = debugger.GetSelectedTarget()
    exe = target.GetExecutable().GetFilename()
    module = target.FindModule(target.GetExecutable())
    cb = module.ResolveFileAddress(CALLBACK_FILE_ADDR).GetLoadAddress(target)

    bw = target.BreakpointCreateByName("IOHIDDeviceSetReport")
    bw.SetScriptCallbackFunction("lldb_capture.on_write")
    bw.SetAutoContinue(True)
    br = target.BreakpointCreateByAddress(cb)
    br.SetScriptCallbackFunction("lldb_capture.on_read")
    br.SetAutoContinue(True)
    LOG.write(f"# attached to {exe}; write bp locs={bw.GetNumLocations()} read cb=0x{cb:x}\n")
    LOG.flush()
    print(f"capture: logging to {LOG.name}; callback at 0x{cb:x}", file=result)


def __lldb_init_module(debugger, internal_dict):
    debugger.HandleCommand("command script add -f lldb_capture.capture capture")
