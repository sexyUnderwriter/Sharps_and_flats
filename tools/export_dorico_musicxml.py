#!/usr/bin/env python3
"""Export every tokenized bar in data/merged_bars.json as one big MusicXML
score, organized as a catalog (grouped by chord, in the app's chord order)
so it can be opened in Dorico to review/edit motifs for playability.

Each bar keeps its own <divisions> (they differ between sources) and its
original internal measure number as the MusicXML measure number, so edits
can be traced back to data/merged_bars.json. A bold text label marks the
first bar of each chord group.

Run: python3 tools/export_dorico_musicxml.py
"""
import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
MERGED = ROOT / "data" / "merged_bars.json"
OUT = ROOT / "Merged Motifs for Dorico.musicxml"

VEX_TO_TYPE = {
    "w": "whole", "h": "half", "q": "quarter", "8": "eighth",
    "16": "16th", "32": "32nd", "64": "64th", "128": "128th",
}


def parse_vex(vex_duration):
    code = vex_duration
    is_rest = code.endswith("r")
    if is_rest:
        code = code[:-1]
    dots = 0
    while code.endswith("d"):
        dots += 1
        code = code[:-1]
    return VEX_TO_TYPE[code], dots, is_rest


def notes_xml(events, voice, staff):
    """Render one staff's raw notation events as <note> elements, tracking
    tuplet ratio across the group (only the tupletStart event carries it)."""
    lines = []
    tuplet_actual = tuplet_normal = None
    for ev in events:
        type_, dots, is_rest = parse_vex(ev["vexDuration"])
        if ev.get("tupletStart"):
            tuplet_actual = ev.get("tupletActual")
            tuplet_normal = ev.get("tupletNormal")
        in_tuplet = tuplet_actual and tuplet_normal

        lines.append("      <note>")
        if is_rest:
            lines.append("        <rest/>")
        else:
            lines.append("        <pitch>")
            lines.append(f"          <step>{ev['step']}</step>")
            if ev.get("alter", 0):
                lines.append(f"          <alter>{ev['alter']}</alter>")
            lines.append(f"          <octave>{ev['octave']}</octave>")
            lines.append("        </pitch>")
        lines.append(f"        <duration>{ev['duration']}</duration>")
        if not is_rest and ev.get("tieStart"):
            lines.append('        <tie type="start"/>')
        if not is_rest and ev.get("tieStop"):
            lines.append('        <tie type="stop"/>')
        lines.append(f"        <voice>{voice}</voice>")
        lines.append(f"        <type>{type_}</type>")
        for _ in range(dots):
            lines.append("        <dot/>")
        if in_tuplet:
            lines.append("        <time-modification>")
            lines.append(f"          <actual-notes>{tuplet_actual}</actual-notes>")
            lines.append(f"          <normal-notes>{tuplet_normal}</normal-notes>")
            lines.append("        </time-modification>")
        lines.append(f"        <staff>{staff}</staff>")

        notations = []
        if not is_rest and ev.get("tieStart"):
            notations.append('<tied type="start"/>')
        if not is_rest and ev.get("tieStop"):
            notations.append('<tied type="stop"/>')
        if ev.get("tupletStart"):
            notations.append('<tuplet type="start"/>')
        if ev.get("tupletStop"):
            notations.append('<tuplet type="stop"/>')
        if notations:
            lines.append("        <notations>")
            lines.extend(f"          {n}" for n in notations)
            lines.append("        </notations>")
        lines.append("      </note>")

        if ev.get("tupletStop"):
            tuplet_actual = tuplet_normal = None
    return lines


def measure_xml(bar, label=None):
    lines = [f'    <measure number="{bar["measure"]}">']
    lines.append("      <attributes>")
    lines.append(f"        <divisions>{bar['divisions']}</divisions>")
    lines.append("      </attributes>")
    if label:
        lines.append('      <direction placement="above">')
        lines.append("        <direction-type>")
        lines.append(f'          <words font-weight="bold" font-size="14">{escape(label)}</words>')
        lines.append("        </direction-type>")
        lines.append("      </direction>")
    lines.extend(notes_xml(bar["trebleNotation"], voice=1, staff=1))
    lines.append(f"      <backup>")
    lines.append(f"        <duration>{bar['ticksPerBar']}</duration>")
    lines.append("      </backup>")
    lines.extend(notes_xml(bar["bassNotation"], voice=2, staff=2))
    lines.append("    </measure>")
    return lines


def main():
    data = json.loads(MERGED.read_text(encoding="utf-8"))
    bars_by_chord = {}
    for bar in data["bars"]:
        bars_by_chord.setdefault(bar["chord"], []).append(bar)

    xml = []
    xml.append('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
    xml.append('<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
               '"http://www.musicxml.org/dtds/partwise.dtd">')
    xml.append('<score-partwise version="4.0">')
    xml.append("  <work><work-title>Merged Motifs for Dorico</work-title></work>")
    xml.append("  <identification><creator type=\"composer\">Composer</creator></identification>")
    xml.append("  <part-list>")
    xml.append('    <score-part id="P1">')
    xml.append("      <part-name>Grand Piano</part-name>")
    xml.append("      <part-abbreviation>Pno.</part-abbreviation>")
    xml.append("    </score-part>")
    xml.append("  </part-list>")
    xml.append('  <part id="P1">')

    first_measure = True
    for chord in data["chordOrder"]:
        bars = bars_by_chord.get(chord, [])
        for i, bar in enumerate(bars):
            label = f"{chord}  ({len(bars)} motifs)" if i == 0 else None
            m_lines = measure_xml(bar, label=label)
            if first_measure:
                # Splice in time/key/clef/tempo setup right after the divisions line.
                insert_at = m_lines.index("      </attributes>")
                setup = [
                    "        <key><fifths>0</fifths></key>",
                    f"        <time><beats>{data['beats']}</beats><beat-type>{data['beatType']}</beat-type></time>",
                    "        <staves>2</staves>",
                    '        <clef number="1"><sign>G</sign><line>2</line></clef>',
                    '        <clef number="2"><sign>F</sign><line>4</line></clef>',
                ]
                m_lines[insert_at:insert_at] = setup
                m_lines.insert(insert_at + len(setup) + 1, f'      <sound tempo="{round(data["tempo"])}"/>')
                first_measure = False
            xml.extend(m_lines)

    xml.append("  </part>")
    xml.append("</score-partwise>")

    OUT.write_text("\n".join(xml) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['bars'])} bars ({len(data['chordOrder'])} chord groups) to {OUT}")


if __name__ == "__main__":
    main()
