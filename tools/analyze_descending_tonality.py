#!/usr/bin/env python3
"""Determine one best-fit triad (tonality) per bar of Descending motifs.xml,
by finding the root+quality whose chord tones cover the most duration-weighted
pitch content of that bar (both staves combined). Skips bars that are silent
in both staves (see tools/xml_to_kern.py).

Labels use the same Roman-numeral convention as the main project (relative to
C, e.g. I/ii/iii/IV/V/vi/i/vidim/viidim), so new chromatic bars found here can
be reviewed before merging into the app's chord vocabulary.

Run: python3 tools/analyze_descending_tonality.py
"""
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_PATH = ROOT / "Descending motifs.xml"
OUT_PATH = ROOT / "analysis" / "descending_motifs_tonality.log"

STEP_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
STEP_DEGREE = {"C": 1, "D": 2, "E": 3, "F": 4, "G": 5, "A": 6, "B": 7}
DEGREE_NUMERAL = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII"}
QUALITY_INTERVALS = {
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "diminished": (0, 3, 6),
}
ACCIDENTAL_SYMBOL = {-1: "b", 0: "", 1: "#"}


def collect_bar_events(measure_el, divisions):
    """Return (weighted_pc_counter, spelling_by_pc, divisions) for one measure.
    weighted_pc_counter: {pitch_class: total_duration}
    spelling_by_pc: {pitch_class: (step, alter)} - most-used spelling in this bar
    """
    weighted = {}
    spelling_weight = {}  # {(pc, (step,alter)): duration}
    last_staff = None
    for child in measure_el:
        if child.tag != "note":
            continue
        last_staff = child.findtext("staff") or last_staff or "1"
        if child.find("rest") is not None:
            continue
        duration = int(child.findtext("duration", "0"))
        pitch = child.find("pitch")
        step = pitch.findtext("step")
        alter = int(pitch.findtext("alter", "0"))
        pc = (STEP_SEMITONES[step] + alter) % 12
        weighted[pc] = weighted.get(pc, 0) + duration
        key = (pc, (step, alter))
        spelling_weight[key] = spelling_weight.get(key, 0) + duration

    spelling_by_pc = {}
    for (pc, spelling), weight in spelling_weight.items():
        if pc not in spelling_by_pc or weight > spelling_by_pc[pc][1]:
            spelling_by_pc[pc] = (spelling, weight)
    spelling_by_pc = {pc: spelling for pc, (spelling, _) in spelling_by_pc.items()}
    return weighted, spelling_by_pc


def best_chord(weighted_pcs):
    """Return (root_pc, quality, score) for the triad covering the most
    duration-weighted content, tie-broken toward diatonic-to-C, lower root."""
    total = sum(weighted_pcs.values())
    if total == 0:
        return None
    best = None
    diatonic_roots = {0, 2, 4, 5, 7, 9, 11}  # C D E F G A B (natural degrees)
    for root in range(12):
        for quality, intervals in QUALITY_INTERVALS.items():
            tones = {(root + i) % 12 for i in intervals}
            score = sum(w for pc, w in weighted_pcs.items() if pc in tones)
            key = (score, root in diatonic_roots, -root)
            if best is None or key > best[0]:
                best = (key, root, quality, score / total)
    _, root, quality, coverage = best
    return root, quality, coverage


def roman_numeral(root_pc, quality, spelling_by_pc):
    step, alter = spelling_by_pc.get(root_pc, (None, None))
    if step is None:
        # No note of this exact pitch class sounded as itself in the bar
        # (root inferred purely from coverage); fall back to a natural spelling.
        NATURAL_BY_PC = {0: ("C", 0), 2: ("D", 0), 4: ("E", 0), 5: ("F", 0), 7: ("G", 0), 9: ("A", 0), 11: ("B", 0)}
        step, alter = NATURAL_BY_PC.get(root_pc, ("C", 0))
    degree = STEP_DEGREE[step]
    numeral = DEGREE_NUMERAL[degree]
    if quality == "minor":
        numeral = numeral.lower()
    elif quality == "diminished":
        numeral = numeral.lower() + "dim"
    prefix = ACCIDENTAL_SYMBOL[max(-1, min(1, alter))]
    return f"{prefix}{numeral}"


PC_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
PC_NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def chord_name(root_pc, quality, spelling_by_pc):
    step, alter = spelling_by_pc.get(root_pc, (None, None))
    if step is not None and alter < 0:
        name = PC_NAMES_FLAT[root_pc]
    elif step is not None and alter > 0:
        name = PC_NAMES_SHARP[root_pc]
    else:
        name = PC_NAMES_SHARP[root_pc]
    qual_label = {"major": "", "minor": "m", "diminished": "dim"}[quality]
    return f"{name}{qual_label}"


def main():
    tree = ET.parse(XML_PATH)
    root_el = tree.getroot()
    part = root_el.find("part")

    divisions = 12
    lines = [
        "Descending motifs - one best-fit chord per bar (both staves combined)",
        "Each bar is an independent motif, analyzed on its own (no assumed shared",
        "key or progression across bars - these are not a single continuous piece).",
        "Roman numerals are relative to C, only as a common label frame so bars",
        "match the existing project vocabulary (I/ii/iii/IV/V/vi/i/vidim/viidim);",
        "other labels are new/chromatic bars to review before merging.",
        "",
    ]

    results = []
    for measure_el in part.findall("measure"):
        measure_num = int(measure_el.get("number"))
        attrs = measure_el.find("attributes")
        if attrs is not None:
            div_text = attrs.findtext("divisions")
            if div_text:
                divisions = int(div_text)

        weighted, spelling_by_pc = collect_bar_events(measure_el, divisions)
        if not weighted:
            continue  # silent bar, omitted (see tools/xml_to_kern.py)

        root_pc, quality, coverage = best_chord(weighted)
        numeral = roman_numeral(root_pc, quality, spelling_by_pc)
        name = chord_name(root_pc, quality, spelling_by_pc)
        results.append((measure_num, numeral, name, coverage))

    for measure_num, numeral, name, coverage in results:
        flag = "  <- weak fit, review (passing/transitional?)" if coverage < 0.6 else ""
        lines.append(f"  {measure_num:3d}  {numeral:6s} {name:5s} (coverage {coverage*100:5.1f}%){flag}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote tonality analysis for {len(results)} bars to {OUT_PATH}")


if __name__ == "__main__":
    main()
