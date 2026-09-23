# Backstory: rescuing an orphaned ECG

How this project came to exist, told in more detail than an article would carry. (The article is
[Using AI to Rescue Old Hardware](https://mcguinnessai.substack.com/p/using-ai-to-rescue-old-hardware).)
Written from my point of view; "Claude" is Claude Code, the AI coding agent I worked with. The work
happened over one long working session.

## The problem

The EMAY EMG-10 is a small handheld ECG. You press your thumbs on its electrodes, and 30 seconds
later it has recorded a single-lead trace, which you can later move to a computer over USB. It's
quietly useful: when something feels off, you can capture it as it happens.

The Mac software for it, "Portable ECG Monitor," is a 2017 Intel-only app. On an Apple silicon Mac it
runs only thanks to Rosetta 2, and macOS now warns that it "will not open in macOS 28, the next major
release." EMAY's current app, "EMAY ECG HD," supports only newer models. There's no documentation of
how the device talks to a computer, and no open-source project for it.

So the device was one OS update away from becoming a paperweight, taking years of recordings with it.

## The detective work

The first thing Claude did was simply look. I plugged the EMG-10 into my Mac and asked whether it
could see it. It couldn't. The device had already gone to sleep, which, I'd learn, it does after
about 30 seconds of idle. Once I woke it up, a new entry appeared on the USB bus: a device calling
itself **"HID Transfer," made by Nuvoton**, with vendor and product IDs of `0x4444` and `0x5555`.

Those numbers are a tell. Nuvoton makes microcontrollers, and "HID Transfer" is the name of their
sample firmware. `4444:5555` look like placeholder IDs, the kind you'd type into a template and never
change. Whoever built this device took a chip maker's example code and shipped it. That's a common
story in cheap consumer hardware, and it meant there would be no documentation to find.

So Claude listened. It opened the device and logged everything it said for 45 seconds while I pressed
buttons. The result was nothing at all. The device doesn't volunteer data; it waits to be spoken to,
in a language we didn't know.

### A false lead

EMAY's current app officially supports only the newer models. Claude downloaded it anyway and looked
inside. Buried in the compiled code was a device check comparing against `0x4444` and `0x5555`: the
exact IDs my EMG-10 reports. Promising.

It swapped in a small logging layer between the app and its USB library, and I clicked "Bind Device."
The app sent a single packet, `81 01` ("what's your name?"), and my device answered:

```
f1 01 02 03 0f 62 01 1e 01 7a 10
```

The app hung up within a millisecond and told me "Get device name timeout." Same USB IDs, different
language. The EMG-10 predates whatever protocol the newer models speak, so the modern app was a dead
end.

(Claude had also tried decompiling that app's code with a Flutter decompiler, only to find the tool
supports Android binaries, not the Windows or Mac builds. Watching the app run turned out to be the
better approach anyway.)

### The app that works, and a clue in its name

Then I found an older app that *could* read the device, "Portable ECG Monitor." Claude checked its
internal identifier: `com.contec.ContecPM10HID`. My EMAY EMG-10 is a **rebadged Contec PM10**, a
Chinese OEM device sold under many brand names. That explained a lot, including why EMAY's own
software had moved on without it.

This app was the key. If Claude could watch it talk to the device, it could learn the language.

### Getting in

The first plan was the same logging layer as before, slipped into the app when it launches. It
loaded, but it didn't catch anything. I dutifully downloaded three recordings and got an empty log.
Claude fixed what it thought was the problem, and I recorded fresh readings and downloaded again.
Empty again. The app, bought from the Mac App Store, has protections that stopped the interception
from taking effect.

So Claude changed tactics and attached a **debugger** (`lldb`) to the running app, the same tool
developers use to step through their own code. From the app's disassembly it found the two places
where the app sends a packet to the device (`IOHIDDeviceSetReport`) and receives one back (the
input-report callback). It set breakpoints there that log each packet and let the app carry on, and
asked me to download one more time.

This time the log filled up: over a thousand packets, every one of them readable.

### The language, decoded

It turned out to be a small protocol:

| The computer says | The device answers | Meaning |
|---|---|---|
| `81` | `f1 …` | Who are you? |
| `82` + date/time | echo | Set your clock |
| `90` | `e0 n` | How many recordings? |
| `fe` | `e1 …` | Next recording's header, one per request |
| `a0` + number | 300 packets | Send me recording N |
| `a0 7f 7f` | – | Goodbye |

A few details made it click:
- **Commands have the high bit set.** Data bytes don't, so every number is sent in 7-bit pieces. The
  year 2026, for example, goes over the wire as `0f 6a` (15 × 128 + 106).
- **The app sets the device clock every time it connects.**
- **Each recording is 300 packets of 25 samples:** 7,500 samples over 30 seconds, which means 250
  samples per second.

And two surprises:
1. **The device held 96 recordings,** going back to 2022. The app had only ever shown me the newest few.
2. **When I clicked "delete" in the app, no command went to the device at all.** "Delete" only removed
   recordings from the app's own list. The data had been sitting on the device the whole time.

Claude turned one captured recording into a plot, and there it was: a clean heartbeat trace, spikes
about once a second, matching the heart rate the device had stored in the header. From plugging the
device in to seeing a heartbeat decoded by software nobody at EMAY wrote took well under an hour.

### Talking to it ourselves

Knowing the language, Claude wrote a small program that speaks it directly, with no vendor app
involved. It connects, sets the clock, and lists every recording with its date and heart rate. The
first run printed all 96.

The full download taught one last lesson. The device powered itself off mid-transfer, about 31
recordings in. It doesn't care that it's busy; after a few minutes, it sleeps. So the downloader
learned to notice the dropout, ask me to wake the device, and pick up where it left off. A couple of
wake-ups later, every recording was saved on my Mac. The vendor's app will soon stop opening on this
Mac; the recordings don't depend on it anymore.

## Making the data useful

Getting the numbers off the device was half the job. Turning them into something worth looking at,
and trustworthy, turned out to be the more interesting half. Much of it was about the difference
between code that runs and results you can believe.

### From squiggles to ECG paper

The first plots were plain line charts. The goal was something that reads like a real ECG strip:
the standard pink grid (1 mm small squares, 5 mm large ones) at the clinical speed of 25 mm per
second, three 10-second rows, with every beat marked. On top of that went a "median beat" panel,
which averages all the beats into one clean complex, with brackets for the standard intervals:
**PR** (atria to ventricles), **QRS** (ventricular activation) and **QT** (ventricular activation
and recovery), plus **QTc**, QT corrected for heart rate.

For finding beats, Claude used an existing open-source library, **NeuroKit2**, rather than writing a
detector from scratch. That part worked well. Its tools for measuring the intervals did not: they
reported QRS widths of 150-180 ms for spikes that were plainly about 50 ms wide.

### The device fights back

The reason was the device itself. Looking closely at the signal revealed three things about what the
EMG-10 stores:
- **It filters everything to 1-20 Hz.** A diagnostic ECG records roughly 0.05-150 Hz, so this blunts
  the sharp edges of each beat.
- **It samples at 250 Hz**, which is coarse for measuring tens of milliseconds.
- **It zeroes out small signals.** The trace sits at exactly zero between waves, a kind of noise gate.
  It's tidy to look at, but it wipes out the small P wave that marks atrial activity.

So Claude kept NeuroKit2 for finding beats and measured the intervals itself, on the median beat,
using textbook methods: QRS starts and ends where the waveform's slope rises and falls, and the end of
the T wave comes from the "tangent method" clinicians use for QT. PR is reported only when a P wave
clearly stands out, which, given the noise gate, is rarely.

### A 10× mistake, caught by a screenshot

To label the vertical axis in millivolts, Claude needed the device's scale: how many raw counts equal
one millivolt. Nothing published says. So it disassembled the Contec app's drawing code and worked the
scale out as 5,000 counts per mV.

With that scale, the traces came out implausibly small, several times below the amplitudes an ECG
normally shows. Claude flagged it as "unverified" rather than trusting it. The fix came from a
screenshot: I opened a recording in the Contec app at its standard 10 mm/mV setting and sent Claude
the picture. Measuring the waves against the grid in the screenshot and comparing them with the raw
data gave **500 counts per mV**, a tenth of what the disassembly suggested. Two independent measurements from the same image agreed within 5%.
The reading of the machine code had been off by a factor of ten; the picture of the app's output was
the better evidence.

### Two kinds of beats, and a ground truth that wasn't

A handheld ECG recording won't always contain complexes of a single shape. A second shape can come
from the heart, or from something as mundane as shifting your grip mid-recording, and a single-lead
trace can't tell which. Either way, the software has to tell the shapes apart before it can measure
anything, and the first attempt went wrong in instructive ways:
- **Detections of wider complexes often landed about 0.1 s late**, on the upswing after them, so they
  looked like a different shape than they were.
- **Pure shape-matching was fragile** on this noise-gated signal, sometimes splitting identical beats
  into two groups.
- **Small T waves were sometimes counted as beats.**

The fix was to locate each beat on its largest deflection in the raw signal, group beats on sturdier
features (polarity, height within 2×, width within 1.5×, plus a loose shape check), drop small
same-polarity detections right after a beat as T waves, and mark shapes that occur only once as
"one-off" (a lone early beat and a movement artifact look the same from one example).

To grade all this, Claude compared our heart rate against the heart rate the device stores with each
recording. Where every beat looks alike, they agree. Where more than one shape appears, the device's
figure tends to land *between* our "all beats" and "main beats only" counts. It evidently counts some
other-shape beats but not all, by a rule nobody outside Contec knows. So the device stopped being
treated as ground truth, and the reports now show both counts next to the device's figure.

There was one more correction. I'd been told the heart rate matched the device "100% of the time"
on clean recordings; when Claude later re-ran the check, it found that figure had been for whichever
of our two rates came closer, not the headline rate. It said so, corrected the number (94%, after an
improvement), and fixed the project notes and a commit message.

### Noise: flag it, don't hide it

I assumed a device squeezed between two thumbs would be full of noise and dropouts, and asked for the
analysis to handle that. Claude measured it first. Hard dropouts turned out to be rare, and the
baseline looked much the same everywhere, thanks to the device's filtering. And the handful of truly
"busy" stretches weren't all noise: an unusual-looking stretch can be exactly the part you'd least
want an algorithm to discard.

So the rule became "flag, don't exclude." Unusually busy 2-second windows are shaded and marked
"check," and nothing is removed from the analysis.

### The device's own verdicts

Each recording carries two small codes that the device's own screening assigns. Claude found their
meaning in a table inside the Contec app: 0 No abnormal, 1 Missed Beat, 2-8 various patterns of
ventricular premature beats (VPBs), 9 Bradycardia, 10 Tachycardia, 11 Arrhythmia (a general
"irregular rhythm" flag), and 12-13 ST elevation or depression. The reports now show the device's
finding with a plain-language explanation, labelled as the device's screening, not a diagnosis.

### Explaining the numbers

Numbers alone aren't much use to a non-cardiologist. Each report now ends with a "What these
measurements mean" section: what each interval measures, its typical adult range, and where this
recording falls. QT's typical range is calculated for the recording's own heart rate, since QT
naturally shortens as the heart speeds up. The wording stays neutral: "within the typical range," or
"above the typical range; a single handheld reading can be off, worth confirming on a clinical ECG."

### What it can't do

- **No atrial fibrillation detection.** AF is recognised by irregular beat spacing *and* missing P
  waves. The noise gate removes the P waves, and other-shape beats make spacing irregular on their
  own, so any AF call from this data would be a guess. The device has no AF category either.
- **No raw data.** The filtering and noise gate happen in the device's firmware before a recording is
  stored, and nothing in the USB protocol or the vendor app's settings offers an unfiltered mode.
- **QRS is imprecise.** Generating a simulated ECG for the README's example image revealed that the
  same beat shape can measure anywhere from 88 to 148 ms depending only on random noise. That's
  noted as an open problem.

## Making it shareable

Before the code could go on GitHub, it had to be safe to publish:
- **Health data stays private.** Recordings were never tracked, notes about the recordings moved
  to a local file, and git history was rewritten to remove the few personal details that had crept in
  earlier. Commits use a GitHub noreply address.
- **The example report is simulated.** It's a synthetic ECG, filtered like the device's output and
  run through the same pipeline, so the README can show a report without showing anyone's heart.
- **License and disclaimers.** The code is MIT-0 (use it freely, no attribution, no warranty, no
  liability), alongside a detailed medical disclaimer, an explicit "intended use: educational and
  research" statement, and a one-time acknowledgement the tool asks for on first run.
- **Provenance.** Library versions are pinned to the ones tested, and every report records the exact
  software versions that produced it, so results can be traced and reproduced.

## What I took from it

Most of the talk about AI coding tools is about building new things. This was **rescue**: pulling a
working device out from under software that's about to stop running.

It worked because of a particular set of conditions:
- **The old app still ran.** Rosetta was still there, so the vendor app could be watched while it
  worked. After macOS 28 that window closes, except on an Intel Mac. I keep a 2017 iMac around for
  exactly that kind of job.
- **The protocol was simple and unencrypted:** six commands and plain bytes.
- **It was my own device, and the recordings on it were ours to access.**

It was also a collaboration, not autopilot. The device falls asleep after 30 seconds, so I spent a
fair amount of the session waking it up. I took test readings, clicked through the vendor apps, and
supplied the screenshot that caught the calibration error. Claude did the digging, the decoding and
the code, and was candid when something it had concluded turned out to be wrong.

The general lesson: if you have a device that depends on aging software, rescue it *before* the
software dies, while you can still watch the old program work.
