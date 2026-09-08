#!/usr/bin/env python3
"""Generate the self-authored playback fixture retrovert_selftest.opi.

An FMP "format 1" module written from scratch: three FM parts on a
four-operator additive patch defined in the file's own tone bank, plus
three SSG parts an octave up, all playing an arpeggiated figure. No PCM,
so the file needs no external sample library. Deterministic output — the
committed fixture and its sha256 in harness.toml must match what this
script emits.
"""

import struct
from pathlib import Path

OUT = Path(__file__).parent / "retrovert_selftest.opi"

# Offsets the driver derives rather than reads: the FM tone bank is pinned
# at 0x1c in this format, and the PCM/PPZ name block and the SSG tone
# pointer sit 0x12 and 2 bytes before the "FMC" signature.
FMTONE = 0x1C
PCMNAME = 0x3C
SSGTONE_PTR = 0x4C
SIGNATURE = 0x4E
TITLE = SIGNATURE + 4

DATA_VERSION = 0x11  # any value <= 0x29 selects the format-1 header

BAR = 96  # the default note length is BAR >> 2
UNUSED = 0xFFFF

CMD_TEMPO = 0x62
CMD_VOLUME = 0x69
CMD_TONE_FM = 0x71
CMD_LOOP = 0x74
CMD_PAN_FM = 0x7C

TEMPO = 0xC8
PAN_BOTH = 0xC0
FM_VOLUME = 12  # index into the driver's FM volume table; 15 is the loudest
SSG_VOLUME = 254  # the driver stores this + 1 and scales by (v-1)/v

# Note numbers are octave * 12 + semitone; 36 is the C of octave 3.
FM_FIGURE = [[36, 40, 43, 48], [40, 43, 48, 52], [43, 48, 52, 55]]
SSG_FIGURE = [[f + 12 for f in voice] for voice in FM_FIGURE]
NOTE_LEN = 24
BARS = 32  # loop body length, so two loops run well past the 10 s smoke


def fm_tone():
    """One 25-byte patch: four operators in parallel (algorithm 7).

    Each group of four bytes is one OPNA register row across the slots,
    in the order the driver replays them: DT/MUL, TL, KS/AR, AM/DR, SR,
    SL/RR, then the feedback/algorithm byte.
    """
    rows = [
        [0x01] * 4,  # detune 0, multiple 1
        [0x00] * 4,  # total level 0, i.e. full output
        [0x1F] * 4,  # no key scaling, fastest attack
        [0x00] * 4,  # no amplitude modulation, no decay
        [0x00] * 4,  # no sustain decay
        [0x0F] * 4,  # sustain at full, fastest release
    ]
    return bytes(b for row in rows for b in row) + bytes((0x07,))


def part_data(figure, fm):
    """Set the part up once, then repeat the figure until the loop."""
    if fm:
        prologue = bytes((CMD_PAN_FM, PAN_BOTH, CMD_TONE_FM, 0, CMD_VOLUME, FM_VOLUME))
    else:
        prologue = bytes((CMD_TEMPO, TEMPO, CMD_VOLUME, SSG_VOLUME))
    body = bytearray()
    for _ in range(BARS):
        for note in figure:
            body += bytes((note, NOTE_LEN))
    body.append(CMD_LOOP)
    return prologue, bytes(body)


def build():
    parts = [part_data(f, fm=True) for f in FM_FIGURE]
    parts += [part_data(f, fm=False) for f in SSG_FIGURE]

    out = bytearray(TITLE)
    out += b"retrovert self-test\0"

    part_ptrs = []
    loop_ptrs = []
    for prologue, body in parts:
        part_ptrs.append(len(out))
        out += prologue
        loop_ptrs.append(len(out))
        out += body

    struct.pack_into("<H", out, 0x00, SIGNATURE)
    for i in range(6):  # FM 1-3 then SSG 1-3, pointers then loop points
        struct.pack_into("<H", out, 0x02 + i * 2, part_ptrs[i])
        struct.pack_into("<H", out, 0x0E + i * 2, loop_ptrs[i])
    out[0x1A] = BAR
    out[0x1B] = 0  # no Q-flag, no PPZ, no LFO octave fix

    out[FMTONE:FMTONE + 25] = fm_tone()
    assert FMTONE + 25 <= PCMNAME
    struct.pack_into("<H", out, SSGTONE_PTR, UNUSED)  # no SSG tone bank
    out[SIGNATURE:SIGNATURE + 4] = b"FMC" + bytes((DATA_VERSION,))

    assert len(out) < 0x10000, "FMP data is addressed with 16-bit pointers"
    return bytes(out)


def main():
    data = build()
    OUT.write_bytes(data)
    print(f"wrote {OUT} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
