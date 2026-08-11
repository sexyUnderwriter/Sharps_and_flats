#!/usr/bin/env python3
"""Tokenize motifs.musicxml into per-bar (measure) assets, tagged with the
chord label from Bars.txt, and write the result to data/bars.json for use
by the web visualizer/player.

Each bar becomes an asset with a treble (staff 1) and bass (staff 2) note
sequence expressed in absolute ticks (MusicXML <divisions> units), so bars
can be freely recombined and played back independently of their original
neighbors in the score. A parallel "notation" sequence (unmerged, keeping
notated type/dots/tuplet/tie info) is also emitted for rendering real sheet
music with VexFlow, alongside the tick-based data used for the piano-roll
graph view and audio playback.
"""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_PATH = ROOT / "motifs.musicxml"
BARS_TXT_PATH = ROOT / "Bars.txt"
OUT_PATH = ROOT / "data" / "bars.json"
# The web app loads this <script> instead of fetch()-ing bars.json, so it
# keeps working when opened via file:// or served with web/ as the root.
JS_OUT_PATH = ROOT / "web" / "bars-data.js"

TYPE_TO_VEX = {
    "whole": "w",
    "half": "h",
    "quarter": "q",
    "eighth": "8",
    "16th": "16",
    "32nd": "32",
    "64th": "64",
    "128th": "128",
}

# Fallback (base_code, dots) for events lacking a notated <type> (e.g. a
# blank measure authored as a single <forward>), keyed by exact tick count
# at divisions=12 (quarter=12 ticks).
FALLBACK_TICKS = {
    48: ("w", 0),
    36: ("h", 1),
    24: ("h", 0),
    18: ("q", 1),
    12: ("q", 0),
    9: ("8", 1),
    6: ("8", 0),
    3: ("16", 0),
}


def parse_chord_ranges(path):
    """Parse lines like '1-35: I' or '245-278; vi dim' into (lo, hi, chord)."""
    ranges = []
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(\d+)\s*-\s*(\d+)\s*[:;]\s*(.+)$", line)
        if not m:
            continue
        lo, hi, chord = int(m.group(1)), int(m.group(2)), m.group(3).strip()
        chord = re.sub(r"\s+dim$", "dim", chord)  # normalize "vi dim" -> "vidim"
        ranges.append((lo, hi, chord))
    return ranges


def chord_for_measure(ranges, measure_num):
    for lo, hi, chord in ranges:
        if lo <= measure_num <= hi:
            return chord
    return "?"


def vex_duration_for(type_text, dots, is_rest, duration, divisions):
    base = TYPE_TO_VEX.get(type_text)
    if base is None:
        # Scale the fallback table (built for divisions=12) to the actual divisions.
        scale = divisions / 12
        base, dots = FALLBACK_TICKS.get(round(duration / scale), ("q", 0))
    code = base + ("d" * dots)
    if is_rest:
        code += "r"
    return code


def to_tick_event(e):
    """Strip an event down to the fields needed for the graph/audio path."""
    if e["type"] == "rest":
        return {"type": "rest", "duration": e["duration"]}
    return {
        "type": "note",
        "step": e["step"],
        "alter": e.get("alter", 0),
        "octave": e["octave"],
        "duration": e["duration"],
    }


def merge_ties(events):
    """Combine a tie-start note with subsequent tie-stop note(s) of the same
    pitch into a single sustained note event (used for graph/audio only)."""
    merged = []
    i = 0
    n = len(events)
    while i < n:
        e = events[i]
        if e["type"] == "note" and e.get("tieStart"):
            total = e["duration"]
            j = i + 1
            while (
                j < n
                and events[j]["type"] == "note"
                and events[j].get("tieStop")
                and events[j]["step"] == e["step"]
                and events[j].get("alter", 0) == e.get("alter", 0)
                and events[j]["octave"] == e["octave"]
            ):
                total += events[j]["duration"]
                keep_going = bool(events[j].get("tieStart"))
                j += 1
                if not keep_going:
                    break
            out = to_tick_event(e)
            out["duration"] = total
            merged.append(out)
            i = j
        else:
            merged.append(to_tick_event(e))
            i += 1
    return merged


def parse_measure(measure_el, divisions):
    """Return {'1': [raw events], '2': [raw events]} keyed by staff number.

    Each raw event keeps notated type/dots/tuplet/tie info for notation
    rendering, plus a precomputed VexFlow duration code.
    """
    voices = {"1": [], "2": []}
    last_staff = None
    for child in measure_el:
        tag = child.tag
        if tag == "note":
            staff = child.findtext("staff") or last_staff or "1"
            last_staff = staff
            duration = int(child.findtext("duration", "0"))
            is_rest = child.find("rest") is not None
            tie_start = any(t.get("type") == "start" for t in child.findall("tie"))
            tie_stop = any(t.get("type") == "stop" for t in child.findall("tie"))
            type_text = child.findtext("type")
            dots = len(child.findall("dot"))
            vex_duration = vex_duration_for(type_text, dots, is_rest, duration, divisions)

            tuplet_start = tuplet_stop = False
            tuplet_actual = tuplet_normal = None
            notations_el = child.find("notations")
            if notations_el is not None:
                for tup in notations_el.findall("tuplet"):
                    if tup.get("type") == "start":
                        tuplet_start = True
                    elif tup.get("type") == "stop":
                        tuplet_stop = True
            if tuplet_start:
                tm = child.find("time-modification")
                if tm is not None:
                    tuplet_actual = int(tm.findtext("actual-notes"))
                    tuplet_normal = int(tm.findtext("normal-notes"))

            entry = {
                "type": "rest" if is_rest else "note",
                "duration": duration,
                "dots": dots,
                "vexDuration": vex_duration,
                "tieStart": tie_start,
                "tieStop": tie_stop,
                "tupletStart": tuplet_start,
                "tupletStop": tuplet_stop,
            }
            if tuplet_actual is not None:
                entry["tupletActual"] = tuplet_actual
                entry["tupletNormal"] = tuplet_normal
            if not is_rest:
                pitch = child.find("pitch")
                entry["step"] = pitch.findtext("step")
                entry["alter"] = int(pitch.findtext("alter", "0"))
                entry["octave"] = int(pitch.findtext("octave"))
            voices.setdefault(staff, []).append(entry)
        elif tag == "forward":
            duration = int(child.findtext("duration", "0"))
            staff = last_staff or "1"
            vex_duration = vex_duration_for(None, 0, True, duration, divisions)
            voices.setdefault(staff, []).append(
                {
                    "type": "rest",
                    "duration": duration,
                    "dots": 0,
                    "vexDuration": vex_duration,
                    "tieStart": False,
                    "tieStop": False,
                    "tupletStart": False,
                    "tupletStop": False,
                }
            )
        elif tag == "backup":
            # Backup only rewinds the authoring cursor to interleave staves;
            # since events are grouped by staff already, no action needed.
            pass
    return voices


def main():
    ranges = parse_chord_ranges(BARS_TXT_PATH)

    tree = ET.parse(XML_PATH)
    root = tree.getroot()
    part = root.find("part")

    divisions = 12
    tempo = 110
    beats, beat_type = 4, 4

    bars = []
    chord_groups = {}

    for measure_el in part.findall("measure"):
        measure_num = int(measure_el.get("number"))

        attrs = measure_el.find("attributes")
        if attrs is not None:
            div_text = attrs.findtext("divisions")
            if div_text:
                divisions = int(div_text)
            time_el = attrs.find("time")
            if time_el is not None:
                beats = int(time_el.findtext("beats", beats))
                beat_type = int(time_el.findtext("beat-type", beat_type))

        sound_el = measure_el.find("sound")
        if sound_el is not None and sound_el.get("tempo"):
            tempo = float(sound_el.get("tempo"))

        chord = chord_for_measure(ranges, measure_num)
        ticks_per_bar = divisions * beats * 4 // beat_type
        raw_voices = parse_measure(measure_el, divisions)

        # A measure with no notated events at all (e.g. a blank bar authored
        # as a single <forward>) is a full-bar rest on both staves.
        for staff_key in ("1", "2"):
            events = raw_voices.get(staff_key) or []
            total = sum(e["duration"] for e in events)
            if total == 0:
                raw_voices[staff_key] = [
                    {
                        "type": "rest",
                        "duration": ticks_per_bar,
                        "dots": 0,
                        "vexDuration": vex_duration_for(None, 0, True, ticks_per_bar, divisions),
                        "tieStart": False,
                        "tieStop": False,
                        "tupletStart": False,
                        "tupletStop": False,
                    }
                ]

        bar = {
            "measure": measure_num,
            "chord": chord,
            "divisions": divisions,
            "ticksPerBar": ticks_per_bar,
            "treble": merge_ties(raw_voices.get("1", [])),
            "bass": merge_ties(raw_voices.get("2", [])),
            "trebleNotation": raw_voices.get("1", []),
            "bassNotation": raw_voices.get("2", []),
        }
        bars.append(bar)
        chord_groups.setdefault(chord, []).append(measure_num)

    data = {
        "tempo": tempo,
        "beats": beats,
        "beatType": beat_type,
        "chordOrder": [c for _, _, c in ranges],
        "chordGroups": chord_groups,
        "bars": bars,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(data, indent=1), encoding="utf-8")

    JS_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JS_OUT_PATH.write_text(
        "window.BARS_DATA = " + json.dumps(data) + ";\n", encoding="utf-8"
    )

    print(f"Wrote {len(bars)} bars across {len(chord_groups)} chord groups to {OUT_PATH} and {JS_OUT_PATH}")


if __name__ == "__main__":
    main()
