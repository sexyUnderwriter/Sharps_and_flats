#!/usr/bin/env python3
"""Export data/merged_bars.json as MusicXML reordered so each phrase sits
immediately next to its inverted-image counterpart (bars with
source="inverted" carry a "derivedFrom" pointing at the original bar's
measure number) -- for reviewing pairs side-by-side in Dorico and spotting
which inversions need melodic smoothing.

Within each chord group (same chordOrder as export_dorico_musicxml.py):
  original bar, its inversion, original bar, its inversion, ...
then any bars with no inverted counterpart, appended at the end of the group.
Each inverted bar carries a small "inversion of m.N" label; each chord group
still gets its bold header (now noting how many pairs it has).

Run: python3 tools/export_dorico_paired.py
"""
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_dorico_musicxml import notes_xml  # reuse note/tie/tuplet rendering

ROOT = Path(__file__).resolve().parent.parent
MERGED = ROOT / "data" / "merged_bars.json"
OUT = ROOT / "Merged Motifs for Dorico (paired).musicxml"


def measure_xml(bar, labels):
    """Like export_dorico_musicxml.measure_xml but supports multiple stacked
    text labels (chord header + pairing annotation) on the same measure."""
    lines = [f'    <measure number="{bar["measure"]}">']
    lines.append("      <attributes>")
    lines.append(f"        <divisions>{bar['divisions']}</divisions>")
    lines.append("      </attributes>")
    for text, bold in labels:
        lines.append('      <direction placement="above">')
        lines.append("        <direction-type>")
        weight = ' font-weight="bold"' if bold else ""
        size = "14" if bold else "10"
        lines.append(f'          <words{weight} font-size="{size}">{escape(text)}</words>')
        lines.append("        </direction-type>")
        lines.append("      </direction>")
    lines.extend(notes_xml(bar["trebleNotation"], voice=1, staff=1))
    lines.append("      <backup>")
    lines.append(f"        <duration>{bar['ticksPerBar']}</duration>")
    lines.append("      </backup>")
    lines.extend(notes_xml(bar["bassNotation"], voice=2, staff=2))
    lines.append("    </measure>")
    return lines


def main():
    data = json.loads(MERGED.read_text(encoding="utf-8"))
    bars = data["bars"]
    inverted_by_source = {b["derivedFrom"]: b for b in bars if b.get("source") == "inverted"}

    bars_by_chord = {}
    for b in bars:
        bars_by_chord.setdefault(b["chord"], []).append(b)

    xml = []
    xml.append('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
    xml.append('<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
               '"http://www.musicxml.org/dtds/partwise.dtd">')
    xml.append('<score-partwise version="4.0">')
    xml.append("  <work><work-title>Merged Motifs for Dorico (paired with inversions)</work-title></work>")
    xml.append("  <identification><creator type=\"composer\">Composer</creator></identification>")
    xml.append("  <part-list>")
    xml.append('    <score-part id="P1">')
    xml.append("      <part-name>Grand Piano</part-name>")
    xml.append("      <part-abbreviation>Pno.</part-abbreviation>")
    xml.append("    </score-part>")
    xml.append("  </part-list>")
    xml.append('  <part id="P1">')

    first_measure = True
    total_pairs = 0
    for chord in data["chordOrder"]:
        chord_bars = bars_by_chord.get(chord, [])
        originals = [b for b in chord_bars if b.get("source") != "inverted"]

        sequence = []
        paired_measures = set()
        for orig in originals:
            inv = inverted_by_source.get(orig["measure"])
            if inv is not None:
                sequence.append((orig, None))
                sequence.append((inv, orig["measure"]))
                paired_measures.add(orig["measure"])
        unpaired = [o for o in originals if o["measure"] not in paired_measures]
        sequence.extend((o, "unpaired") for o in unpaired)

        n_pairs = len(paired_measures)
        total_pairs += n_pairs

        for i, (bar, tag) in enumerate(sequence):
            labels = []
            if i == 0:
                labels.append((f"{chord}  ({len(originals)} motifs, {n_pairs} paired w/ inversion)", True))
            if tag == "unpaired":
                if n_pairs > 0 and (i == 0 or sequence[i - 1][1] != "unpaired"):
                    labels.append(("\u2014 unpaired (no inversion) \u2014", True))
            elif tag is not None:
                labels.append((f"inversion of m.{tag}", False))

            m_lines = measure_xml(bar, labels)
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
    print(f"Wrote {len(bars)} bars ({total_pairs} pairs = {total_pairs * 2} paired measures) to {OUT}")


if __name__ == "__main__":
    main()
