#!/usr/bin/env python3
"""Merge "Descending motifs.xml" into the app's chord-tagged bar library,
producing data/bars_merged.json + web/bars-data.js so all of these motifs
become bar-variant options in the running app alongside the main piece.

Each Descending motifs bar is scored independently for its own best-fit triad
(same approach as tools/analyze_descending_tonality.py - these are separate
motifs, not one continuous piece) and merged under that chord label, adding
new chord categories to the vocabulary where needed. Measure numbers are
offset by MEASURE_OFFSET so they stay unique from the main piece's 1-313
range.

Run: python3 tools/merge_descending_motifs.py
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tokenize_bars as tb
import analyze_descending_tonality as adt

ROOT = Path(__file__).resolve().parent.parent
MAIN_BARS_JSON = ROOT / "data" / "bars.json"
DESCENDING_XML = ROOT / "Descending motifs.xml"
MERGED_JSON = ROOT / "data" / "bars_merged.json"
MERGED_JS = ROOT / "web" / "bars-data.js"

MEASURE_OFFSET = 1000  # keeps Descending motifs' bar numbers unique from the main piece's 1-313


def descending_bars():
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

        weighted, spelling_by_pc = adt.collect_bar_events(measure_el, divisions)
        if not weighted:
            continue  # silent bar - no chord to assign, skip (see tools/xml_to_kern.py)

        root_pc, quality, _coverage = adt.best_chord(weighted)
        chord = adt.roman_numeral(root_pc, quality, spelling_by_pc)

        ticks_per_bar = divisions * beats * 4 // beat_type
        raw_voices = tb.parse_measure(measure_el, divisions)
        for staff_key in ("1", "2"):
            events = raw_voices.get(staff_key) or []
            if sum(e["duration"] for e in events) == 0:
                raw_voices[staff_key] = [
                    {
                        "type": "rest",
                        "duration": ticks_per_bar,
                        "dots": 0,
                        "vexDuration": tb.vex_duration_for(None, 0, True, ticks_per_bar, divisions),
                        "tieStart": False,
                        "tieStop": False,
                        "tupletStart": False,
                        "tupletStop": False,
                    }
                ]

        bars.append(
            {
                "measure": measure_num + MEASURE_OFFSET,
                "chord": chord,
                "divisions": divisions,
                "ticksPerBar": ticks_per_bar,
                "treble": tb.merge_ties(raw_voices.get("1", [])),
                "bass": tb.merge_ties(raw_voices.get("2", [])),
                "trebleNotation": raw_voices.get("1", []),
                "bassNotation": raw_voices.get("2", []),
                "source": "Descending motifs",
            }
        )
    return bars


def main():
    data = json.loads(MAIN_BARS_JSON.read_text(encoding="utf-8"))
    original_chords = set(data["chordGroups"])
    new_bars = descending_bars()

    for bar in new_bars:
        data["bars"].append(bar)
        data["chordGroups"].setdefault(bar["chord"], []).append(bar["measure"])
        if bar["chord"] not in data["chordOrder"]:
            data["chordOrder"].append(bar["chord"])

    MERGED_JSON.parent.mkdir(parents=True, exist_ok=True)
    MERGED_JSON.write_text(json.dumps(data, indent=1), encoding="utf-8")
    MERGED_JS.parent.mkdir(parents=True, exist_ok=True)
    MERGED_JS.write_text("window.BARS_DATA = " + json.dumps(data) + ";\n", encoding="utf-8")

    new_chords = sorted({b["chord"] for b in new_bars} - original_chords)
    print(f"Merged {len(new_bars)} bars from {DESCENDING_XML.name} into {len(data['bars'])} total bars.")
    print(f"New chord categories added: {new_chords}")
    print(f"Wrote {MERGED_JSON} and {MERGED_JS} (app now loads the merged set)")


if __name__ == "__main__":
    main()
