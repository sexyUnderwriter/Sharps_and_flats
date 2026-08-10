#!/usr/bin/env python3
"""Tokenize motifs.musicxml into per-bar (measure) assets, tagged with the
chord label from Bars.txt, and write the result to data/bars.json for use
by the web visualizer/player.

Each bar becomes an asset with a treble (staff 1) and bass (staff 2) note
sequence expressed in absolute ticks (MusicXML <divisions> units), so bars
can be freely recombined and played back independently of their original
neighbors in the score.
"""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_PATH = ROOT / "motifs.musicxml"
BARS_TXT_PATH = ROOT / "Bars.txt"
OUT_PATH = ROOT / "data" / "bars.json"


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


def merge_ties(events):
    """Combine a tie-start note with subsequent tie-stop note(s) of the same
    pitch into a single sustained note event."""
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
            new_e = {k: v for k, v in e.items() if k not in ("tieStart", "tieStop")}
            new_e["duration"] = total
            merged.append(new_e)
            i = j
        else:
            clean = {k: v for k, v in e.items() if k not in ("tieStart", "tieStop")}
            merged.append(clean)
            i += 1
    return merged


def parse_measure(measure_el):
    """Return {'1': [events], '2': [events]} keyed by staff number."""
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
            if is_rest:
                voices.setdefault(staff, []).append(
                    {"type": "rest", "duration": duration}
                )
            else:
                pitch = child.find("pitch")
                step = pitch.findtext("step")
                alter = int(pitch.findtext("alter", "0"))
                octave = int(pitch.findtext("octave"))
                voices.setdefault(staff, []).append(
                    {
                        "type": "note",
                        "step": step,
                        "alter": alter,
                        "octave": octave,
                        "duration": duration,
                        "tieStart": tie_start,
                        "tieStop": tie_stop,
                    }
                )
        elif tag == "forward":
            duration = int(child.findtext("duration", "0"))
            staff = last_staff or "1"
            voices.setdefault(staff, []).append({"type": "rest", "duration": duration})
        elif tag == "backup":
            # Backup only rewinds the authoring cursor to interleave staves;
            # since events are grouped by staff already, no action needed.
            pass
    return {staff: merge_ties(events) for staff, events in voices.items()}


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
        voices = parse_measure(measure_el)
        ticks_per_bar = divisions * beats * 4 // beat_type

        # A measure with no notated events at all (e.g. a blank bar authored
        # as a single <forward>) is a full-bar rest on both staves.
        for staff_key in ("1", "2"):
            events = voices.get(staff_key) or []
            total = sum(e["duration"] for e in events)
            if total == 0:
                voices[staff_key] = [{"type": "rest", "duration": ticks_per_bar}]

        bar = {
            "measure": measure_num,
            "chord": chord,
            "divisions": divisions,
            "ticksPerBar": ticks_per_bar,
            "treble": voices.get("1", []),
            "bass": voices.get("2", []),
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
    print(f"Wrote {len(bars)} bars across {len(chord_groups)} chord groups to {OUT_PATH}")


if __name__ == "__main__":
    main()
