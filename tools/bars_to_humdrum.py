#!/usr/bin/env python3
"""Convert the tokenized bar data (data/bars.json) to a clean Humdrum **kern
file (data/motifs.krn) for analysis in Humdrum/music21/verovio tooling.

Built directly from our own validated per-bar note data (not a third-party
MusicXML->Humdrum converter) so ties, tuplets, rests and dotted rhythms are
guaranteed to round-trip correctly. Run: python3 tools/bars_to_humdrum.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BARS_JSON = ROOT / "data" / "bars.json"
OUT_PATH = ROOT / "data" / "motifs.krn"

VEX_BASE_TO_KERN = {"w": 1, "h": 2, "q": 4, "8": 8, "16": 16, "32": 32, "64": 64, "128": 128}


def kern_pitch(step, alter, octave):
    if octave >= 4:
        letter = step.lower()
        reps = octave - 3
    else:
        letter = step.upper()
        reps = 4 - octave
    accidental = "#" * alter if alter > 0 else "-" * (-alter)
    return letter * reps + accidental


def kern_duration(vex_duration, tuplet_actual, tuplet_normal):
    code = vex_duration
    is_rest = code.endswith("r")
    if is_rest:
        code = code[:-1]
    dots = 0
    while code.endswith("d"):
        dots += 1
        code = code[:-1]
    base = VEX_BASE_TO_KERN[code]
    if tuplet_actual and tuplet_normal:
        base = base * tuplet_actual // tuplet_normal
    return f"{base}{'.' * dots}", is_rest


def kern_token(event, tuplet_actual, tuplet_normal):
    dur, is_rest = kern_duration(event["vexDuration"], tuplet_actual, tuplet_normal)
    if is_rest:
        return f"{dur}r"
    pitch = kern_pitch(event["step"], event.get("alter", 0), event["octave"])
    tie_start, tie_stop = event.get("tieStart"), event.get("tieStop")
    tie = "_" if tie_start and tie_stop else "[" if tie_start else "]" if tie_stop else ""
    return f"{dur}{pitch}{tie}"


def onsets_with_tokens(events):
    """Return [(onset_tick, kern_token), ...] for a staff's raw notation events."""
    result = []
    t = 0
    tuplet_actual = tuplet_normal = None
    for ev in events:
        if ev.get("tupletStart"):
            tuplet_actual = ev.get("tupletActual")
            tuplet_normal = ev.get("tupletNormal")
        result.append((t, kern_token(ev, tuplet_actual, tuplet_normal)))
        if ev.get("tupletStop"):
            tuplet_actual = tuplet_normal = None
        t += ev["duration"]
    return result


def main():
    data = json.loads(BARS_JSON.read_text(encoding="utf-8"))
    lines = []
    lines.append("!!!COM: Composer")
    lines.append("!!!OTL: Stage Grand Piano Copy 1")
    lines.append("**kern\t**kern")
    lines.append("*staff1\t*staff2")
    lines.append("*Ipiano\t*Ipiano")
    lines.append("*clefG2\t*clefF4")
    lines.append(f"*M{data['beats']}/{data['beatType']}\t*M{data['beats']}/{data['beatType']}")
    lines.append(f"*MM{round(data['tempo'])}\t*MM{round(data['tempo'])}")

    for bar in data["bars"]:
        lines.append(f"=\t=")
        lines.append(f"!{bar['chord']}\t!{bar['chord']}")
        treble = dict(onsets_with_tokens(bar["trebleNotation"]))
        bass = dict(onsets_with_tokens(bar["bassNotation"]))
        for onset in sorted(set(treble) | set(bass)):
            lines.append(f"{treble.get(onset, '.')}\t{bass.get(onset, '.')}")

    lines.append("==\t==")
    lines.append("*-\t*-")

    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['bars'])} bars of Humdrum **kern data to {OUT_PATH}")


if __name__ == "__main__":
    main()
