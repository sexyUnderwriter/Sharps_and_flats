#!/usr/bin/env python3
"""Merge the main motifs.musicxml bars (data/bars.json) with the Descending
motifs.xml bars into one combined asset library for the app, using a single
standard chord-naming scheme (letter names with C as the tonic reference,
e.g. "C", "Dm", "Bdim") instead of the two different labeling styles each
source started with.

- motifs.musicxml bars keep their original curated Bars.txt grouping, just
  relabeled from Roman numerals to the standard name that best matches that
  group's actual harmony (majority vote across the group's bars).
- Descending motifs.xml bars are each tagged independently (no shared key
  assumed - see analysis/descending_motifs_tonality.log) with the standard
  chord name that best covers that bar's own pitch content. Bars silent in
  both staves are skipped (same rule as tools/xml_to_kern.py). Measure
  numbers are offset by 1000 to avoid colliding with motifs.musicxml's 1-313.

Writes data/merged_bars.json (canonical merged data) and regenerates
web/bars-data.js from it so the app actually uses the combined set.

Run: python3 tools/merge_motifs.py
"""
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BARS_JSON = ROOT / "data" / "bars.json"
DESCENDING_XML = ROOT / "Descending motifs.xml"
MERGED_OUT = ROOT / "data" / "merged_bars.json"
JS_OUT = ROOT / "web" / "bars-data.js"
DESCENDING_MEASURE_OFFSET = 1000

# Standard chord name each curated motifs.musicxml group empirically matches
# best (majority vote of best-fit triad per bar in that group).
ROMAN_TO_STANDARD = {
    "I": "C",
    "IV": "F",
    "V": "G",
    "ii": "Dm",
    "vi": "Am",
    "iii": "Em",
    "i": "Cm",
    "vidim": "Gm",
    "viidim": "Bdim",
}

STEP_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
QUALITY_INTERVALS = {"major": (0, 4, 7), "minor": (0, 3, 7), "diminished": (0, 3, 6)}
PC_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

TYPE_TO_VEX = {
    "whole": "w", "half": "h", "quarter": "q", "eighth": "8",
    "16th": "16", "32nd": "32", "64th": "64", "128th": "128",
}
VEX_BASE_TO_KERN = {"w": 1, "h": 2, "q": 4, "8": 8, "16": 16, "32": 32, "64": 64, "128": 128}
FALLBACK_TICKS = {
    48: ("w", 0), 36: ("h", 1), 24: ("h", 0), 18: ("q", 1),
    12: ("q", 0), 9: ("8", 1), 6: ("8", 0), 3: ("16", 0),
}


def vex_duration_for(type_text, dots, is_rest, duration, divisions):
    base = TYPE_TO_VEX.get(type_text)
    if base is None:
        scale = divisions / 12
        base, dots = FALLBACK_TICKS.get(round(duration / scale), ("q", 0))
    code = base + ("d" * dots)
    if is_rest:
        code += "r"
    return code


def to_tick_event(e):
    if e["type"] == "rest":
        return {"type": "rest", "duration": e["duration"]}
    return {"type": "note", "step": e["step"], "alter": e.get("alter", 0), "octave": e["octave"], "duration": e["duration"]}


def merge_ties(events):
    merged = []
    i, n = 0, len(events)
    while i < n:
        e = events[i]
        if e["type"] == "note" and e.get("tieStart"):
            total = e["duration"]
            j = i + 1
            while (j < n and events[j]["type"] == "note" and events[j].get("tieStop")
                   and events[j]["step"] == e["step"] and events[j].get("alter", 0) == e.get("alter", 0)
                   and events[j]["octave"] == e["octave"]):
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
            voices.setdefault(staff, []).append({
                "type": "rest", "duration": duration, "dots": 0,
                "vexDuration": vex_duration_for(None, 0, True, duration, divisions),
                "tieStart": False, "tieStop": False, "tupletStart": False, "tupletStop": False,
            })
        # backup only rewinds the authoring cursor; events are grouped by staff already
    return voices


def best_chord_name(events_by_staff):
    """Duration-weighted best-fit root+quality triad across both staves, as a
    standard chord-letter name (e.g. "Dm"), or None if the bar has no notes."""
    weighted = Counter()
    for events in events_by_staff:
        for e in events:
            if e["type"] == "note":
                pc = (STEP_SEMITONES[e["step"]] + e.get("alter", 0)) % 12
                weighted[pc] += e["duration"]
    total = sum(weighted.values())
    if total == 0:
        return None
    best = None
    for root in range(12):
        for quality, intervals in QUALITY_INTERVALS.items():
            tones = {(root + i) % 12 for i in intervals}
            score = sum(w for pc, w in weighted.items() if pc in tones)
            key = (score, -root)
            if best is None or key > best[0]:
                best = (key, root, quality)
    _, root, quality = best
    qual_label = {"major": "", "minor": "m", "diminished": "dim"}[quality]
    return f"{PC_NAMES_SHARP[root]}{qual_label}"


MAJOR_THIRD_SEMITONES = 4
LETTER_INDEX = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
LETTERS = "CDEFGAB"

# Diatonic scale (alter per natural letter) each chord's melodies are drawn
# from, used as the reference collection for melodic inversion.
MAJOR_CONTEXT_SCALE = {l: 0 for l in LETTERS}
MINOR_CONTEXT_SCALE = {"C": 0, "D": 0, "E": -1, "F": 0, "G": 0, "A": -1, "B": -1}
CHORD_SCALE = {
    "C": MAJOR_CONTEXT_SCALE, "F": MAJOR_CONTEXT_SCALE, "G": MAJOR_CONTEXT_SCALE,
    "Dm": MAJOR_CONTEXT_SCALE, "Am": MAJOR_CONTEXT_SCALE, "Em": MAJOR_CONTEXT_SCALE,
    "Cm": MINOR_CONTEXT_SCALE, "Gm": MINOR_CONTEXT_SCALE, "Bdim": MINOR_CONTEXT_SCALE,
}
# Chords whose "falling" pool is thin (see analysis/voice_leading_merged.log);
# these get supplemented by diatonically inverting their "rising" bars.
THIN_FALLING_CHORDS = ["F", "G", "Dm", "Am", "Em", "Cm", "Gm", "Bdim"]


def midi(note):
    return (note["octave"] + 1) * 12 + STEP_SEMITONES[note["step"]] + note.get("alter", 0)


def classify_contour(events):
    notes = [e for e in events if e["type"] == "note"]
    if not notes:
        return "neither"
    diff = midi(notes[-1]) - midi(notes[0])
    if diff > MAJOR_THIRD_SEMITONES:
        return "rising"
    if diff < -MAJOR_THIRD_SEMITONES:
        return "falling"
    return "neither"


def invert_note_diatonically(note, scale, pivot_position):
    """Mirror one note's staff position (letter+octave) around pivot_position,
    then re-derive its alteration from the target scale, preserving (mirrored)
    any chromatic deviation the original note had from that scale."""
    position = note["octave"] * 7 + LETTER_INDEX[note["step"]]
    mirrored = 2 * pivot_position - position
    new_octave, degree = divmod(mirrored, 7)
    new_step = LETTERS[degree]
    chromatic_offset = note.get("alter", 0) - scale[note["step"]]
    new_alter = scale[new_step] - chromatic_offset
    return {**note, "step": new_step, "alter": new_alter, "octave": new_octave}


def invert_treble_diatonically(events, scale):
    notes_only = [e for e in events if e["type"] == "note"]
    if not notes_only:
        return None
    pivot = notes_only[0]["octave"] * 7 + LETTER_INDEX[notes_only[0]["step"]]
    return [invert_note_diatonically(e, scale, pivot) if e["type"] == "note" else e for e in events]


def build_inverted_falling_bars(bars, next_measure_start):
    """For chords with few "falling" bars, diatonically invert their "rising"
    bars' treble melody (bass/harmony untouched) to create new falling bars.
    Only keeps a result if it actually classifies as falling afterward."""
    inverted = []
    next_measure = next_measure_start
    for bar in bars:
        chord = bar["chord"]
        if chord not in THIN_FALLING_CHORDS:
            continue
        if classify_contour(bar["treble"]) != "rising":
            continue
        scale = CHORD_SCALE[chord]
        new_treble_notation = invert_treble_diatonically(bar["trebleNotation"], scale)
        if new_treble_notation is None:
            continue
        new_treble = merge_ties(new_treble_notation)
        if classify_contour(new_treble) != "falling":
            continue
        inverted.append({
            **bar,
            "measure": next_measure,
            "source": "inverted",
            "derivedFrom": bar["measure"],
            "treble": new_treble,
            "trebleNotation": new_treble_notation,
        })
        next_measure += 1
    return inverted


def build_descending_bars():
    tree = ET.parse(DESCENDING_XML)
    part = tree.getroot().find("part")

    divisions = 12
    beats, beat_type = 4, 4
    bars = []
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

        raw_voices = parse_measure(measure_el, divisions)
        chord = best_chord_name([raw_voices.get("1", []), raw_voices.get("2", [])])
        if chord is None:
            continue  # silent in both staves - not a usable playable bar

        ticks_per_bar = divisions * beats * 4 // beat_type

        # A staff with zero notated duration (e.g. a bar where the composer
        # left the bass empty with no rest) is a full-bar rest on that staff.
        for staff_key in ("1", "2"):
            events = raw_voices.get(staff_key) or []
            if sum(e["duration"] for e in events) == 0:
                raw_voices[staff_key] = [{
                    "type": "rest", "duration": ticks_per_bar, "dots": 0,
                    "vexDuration": vex_duration_for(None, 0, True, ticks_per_bar, divisions),
                    "tieStart": False, "tieStop": False, "tupletStart": False, "tupletStop": False,
                }]

        bars.append({
            "measure": measure_num + DESCENDING_MEASURE_OFFSET,
            "chord": chord,
            "source": "descending",
            "divisions": divisions,
            "ticksPerBar": ticks_per_bar,
            "treble": merge_ties(raw_voices.get("1", [])),
            "bass": merge_ties(raw_voices.get("2", [])),
            "trebleNotation": raw_voices.get("1", []),
            "bassNotation": raw_voices.get("2", []),
        })
    return bars


def main():
    data = json.loads(BARS_JSON.read_text(encoding="utf-8"))

    motifs_bars = []
    for bar in data["bars"]:
        bar = dict(bar)
        bar["chord"] = ROMAN_TO_STANDARD[bar["chord"]]
        bar["source"] = "motifs"
        motifs_bars.append(bar)

    descending_bars = build_descending_bars()

    inverted_bars = build_inverted_falling_bars(motifs_bars + descending_bars, next_measure_start=2001)

    all_bars = motifs_bars + descending_bars + inverted_bars
    chord_order = []
    for label in ROMAN_TO_STANDARD.values():
        if label not in chord_order:
            chord_order.append(label)
    chord_groups = {}
    for bar in all_bars:
        chord_groups.setdefault(bar["chord"], []).append(bar["measure"])
        if bar["chord"] not in chord_order:
            chord_order.append(bar["chord"])

    merged = {
        "tempo": data["tempo"],
        "beats": data["beats"],
        "beatType": data["beatType"],
        "chordOrder": chord_order,
        "chordGroups": chord_groups,
        "bars": all_bars,
    }

    MERGED_OUT.parent.mkdir(parents=True, exist_ok=True)
    MERGED_OUT.write_text(json.dumps(merged, indent=1), encoding="utf-8")
    JS_OUT.write_text("window.BARS_DATA = " + json.dumps(merged) + ";\n", encoding="utf-8")

    print(f"Merged {len(motifs_bars)} motifs bars + {len(descending_bars)} descending bars "
          f"+ {len(inverted_bars)} diatonically-inverted falling bars "
          f"= {len(all_bars)} bars across {len(chord_groups)} chords")
    print(f"Wrote {MERGED_OUT} and {JS_OUT}")


if __name__ == "__main__":
    main()
