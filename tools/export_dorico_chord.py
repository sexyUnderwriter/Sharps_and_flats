#!/usr/bin/env python3
"""Export only the bars for one chord (default: C major) from
data/merged_bars.json as MusicXML for Dorico -- a focused subset of the
full "Merged Motifs for Dorico" export, same bar order as in merged_bars.json.

Usage: python3 tools/export_dorico_chord.py [CHORD]
  (CHORD defaults to "C"; must match a value in merged_bars.json's chordOrder)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_dorico_musicxml import measure_xml

ROOT = Path(__file__).resolve().parent.parent
MERGED = ROOT / "data" / "merged_bars.json"


def main():
    chord = sys.argv[1] if len(sys.argv) > 1 else "C"
    label = "C major" if chord == "C" else chord
    out = ROOT / f"Merged Motifs for Dorico ({label}).musicxml"

    data = json.loads(MERGED.read_text(encoding="utf-8"))
    bars = [b for b in data["bars"] if b["chord"] == chord]
    if not bars:
        sys.exit(f"No bars found for chord {chord!r} (chordOrder: {data['chordOrder']})")

    xml = []
    xml.append('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
    xml.append('<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
               '"http://www.musicxml.org/dtds/partwise.dtd">')
    xml.append('<score-partwise version="4.0">')
    xml.append(f"  <work><work-title>Merged Motifs for Dorico - {label}</work-title></work>")
    xml.append("  <identification><creator type=\"composer\">Composer</creator></identification>")
    xml.append("  <part-list>")
    xml.append('    <score-part id="P1">')
    xml.append("      <part-name>Grand Piano</part-name>")
    xml.append("      <part-abbreviation>Pno.</part-abbreviation>")
    xml.append("    </score-part>")
    xml.append("  </part-list>")
    xml.append('  <part id="P1">')

    first_measure = True
    for i, bar in enumerate(bars):
        bar_label = f"{label}  ({len(bars)} motifs)" if i == 0 else None
        m_lines = measure_xml(bar, label=bar_label)
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

    out.write_text("\n".join(xml) + "\n", encoding="utf-8")
    print(f"Wrote {len(bars)} bars for chord {chord!r} to {out}")


if __name__ == "__main__":
    main()
