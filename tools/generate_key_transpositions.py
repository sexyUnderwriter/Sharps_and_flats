#!/usr/bin/env python3
"""Transpose the hand-corrected "C major" Dorico master (78 measures -- voice
leading/register already reviewed by hand in Dorico) into all 24 major/minor
keys. Diminished chords are skipped (handled separately by the user).

Master source (NOT data/merged_bars.json -- per instruction to use "the
Dorico version", which has manual fixes the JSON pipeline doesn't have):
  "Flows from Merged Motifs for Dorico - C major/Merged Motifs for Dorico -
  C major - Full score - 01 Merged Motifs for Dorico - C major.musicxml"

Transposition: each note's diatonic letter position is shifted 0-6 steps
(always ascending, less than an octave) to match the target tonic's own
letter name, then its accidental is re-derived from the target key's own
scale (standard key signature) while preserving any chromatic deviation the
source note had from plain C major -- same technique as merge_motifs.py's
build_inverted_falling_bars (invert_note_diatonically), but transposing
instead of mirroring. Every motif is treated as belonging to the same "key"
regardless of its original chord -- the whole master is shifted as one block
per target key.

Register cap: after transposition, if a measure (either staff) has a note
below F2 (MIDI 41) or above C6 (MIDI 84), the WHOLE measure (both staves) is
shifted by one octave toward the violated bound -- a single nudge only, per
instruction. Motifs spanning more than an octave beyond a bound may still be
out of range afterward; these are printed as flagged measures per key for
manual correction.

Run: python3 tools/generate_key_transpositions.py
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xml_to_kern import parse_measure
from export_dorico_musicxml import measure_xml

ROOT = Path(__file__).resolve().parent.parent
MASTER = (ROOT / "Flows from Merged Motifs for Dorico - C major" /
          "Merged Motifs for Dorico - C major - Full score - "
          "01 Merged Motifs for Dorico - C major.musicxml")

LETTERS = "CDEFGAB"
LETTER_INDEX = {l: i for i, l in enumerate(LETTERS)}
STEP_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SHARP_ORDER = "FCGDAEB"
FLAT_ORDER = "BEADGCF"

MIN_MIDI = 41  # F2
MAX_MIDI = 84  # C6

# (label, tonic letter, sharps, flats) -- ascending transposition from C,
# 0-11 semitones, standard key signatures (major sharp side C..F#, flat side
# F..Db; minor sharp side Am..D#m, flat side Dm..Bbm), covering each of the
# 12 semitones exactly once per mode.
MAJOR_KEYS = [
    ("C major", "C", 0, 0), ("Db major", "D", 0, 5), ("D major", "D", 2, 0),
    ("Eb major", "E", 0, 3), ("E major", "E", 4, 0), ("F major", "F", 0, 1),
    ("F# major", "F", 6, 0), ("G major", "G", 1, 0), ("Ab major", "A", 0, 4),
    ("A major", "A", 3, 0), ("Bb major", "B", 0, 2), ("B major", "B", 5, 0),
]
MINOR_KEYS = [
    ("C minor", "C", 0, 3), ("C# minor", "C", 4, 0), ("D minor", "D", 0, 1),
    ("D# minor", "D", 6, 0), ("E minor", "E", 1, 0), ("F minor", "F", 0, 4),
    ("F# minor", "F", 3, 0), ("G minor", "G", 0, 2), ("G# minor", "G", 5, 0),
    ("A minor", "A", 0, 0), ("Bb minor", "B", 0, 5), ("B minor", "B", 2, 0),
]


def key_scale(sharps, flats):
    scale = {l: 0 for l in LETTERS}
    for l in SHARP_ORDER[:sharps]:
        scale[l] = 1
    for l in FLAT_ORDER[:flats]:
        scale[l] = -1
    return scale


SOURCE_SCALE = key_scale(0, 0)  # master is plain C major, no accidentals baseline


def transpose_note(note, shift, target_scale):
    position = note["octave"] * 7 + LETTER_INDEX[note["step"]]
    new_octave, degree = divmod(position + shift, 7)
    new_step = LETTERS[degree]
    chromatic_offset = note.get("alter", 0) - SOURCE_SCALE[note["step"]]
    new_alter = target_scale[new_step] + chromatic_offset
    return {**note, "step": new_step, "alter": new_alter, "octave": new_octave}


def transpose_events(events, shift, target_scale):
    return [transpose_note(e, shift, target_scale) if e["type"] == "note" else dict(e) for e in events]


def midi(note):
    return (note["octave"] + 1) * 12 + STEP_SEMITONES[note["step"]] + note.get("alter", 0)


def cap_register(treble, bass):
    """If any note in the bar is outside [F2, C6], shift the whole bar (both
    staves) by one octave toward the violated bound. Returns
    (treble, bass, still_out_of_range)."""
    notes = [e for e in treble + bass if e["type"] == "note"]
    if not notes:
        return treble, bass, False
    lo, hi = min(midi(n) for n in notes), max(midi(n) for n in notes)
    shift_oct = -1 if hi > MAX_MIDI else 1 if lo < MIN_MIDI else 0
    if shift_oct:
        treble = [{**e, "octave": e["octave"] + shift_oct} if e["type"] == "note" else e for e in treble]
        bass = [{**e, "octave": e["octave"] + shift_oct} if e["type"] == "note" else e for e in bass]
        notes = [e for e in treble + bass if e["type"] == "note"]
        lo, hi = min(midi(n) for n in notes), max(midi(n) for n in notes)
    return treble, bass, hi > MAX_MIDI or lo < MIN_MIDI


def parse_master():
    tree = ET.parse(MASTER)
    part = tree.getroot().find("part")
    divisions = 12
    beats, beat_type = 4, 4
    bars = []
    for measure_el in part.findall("measure"):
        attrs = measure_el.find("attributes")
        if attrs is not None:
            div_text = attrs.findtext("divisions")
            if div_text:
                divisions = int(div_text)
            time_el = attrs.find("time")
            if time_el is not None:
                beats = int(time_el.findtext("beats", beats))
                beat_type = int(time_el.findtext("beat-type", beat_type))
        raw = parse_measure(measure_el, divisions)
        bars.append({
            "divisions": divisions,
            "ticksPerBar": divisions * beats * 4 // beat_type,
            "treble": raw.get("1", []),
            "bass": raw.get("2", []),
        })
    # Last 3 measures are a trailing whole-bar-rest artifact (both staves
    # silent) -- not part of the actual motif set.
    bars = bars[:-3]
    return bars, beats, beat_type


def write_key_file(label, mode, fifths, bars, beats, beat_type, shift, target_scale):
    out = ROOT / f"Merged Motifs for Dorico - {label}.musicxml"
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

    flagged = []
    first_measure = True
    for i, bar in enumerate(bars, start=1):
        treble = transpose_events(bar["treble"], shift, target_scale)
        bass = transpose_events(bar["bass"], shift, target_scale)
        treble, bass, still_bad = cap_register(treble, bass)
        if still_bad:
            flagged.append(i)

        out_bar = {
            "measure": i,
            "divisions": bar["divisions"],
            "ticksPerBar": bar["ticksPerBar"],
            "trebleNotation": treble,
            "bassNotation": bass,
        }
        bar_label = f"{label}  ({len(bars)} motifs)" if i == 1 else None
        m_lines = measure_xml(out_bar, label=bar_label)
        if first_measure:
            insert_at = m_lines.index("      </attributes>")
            setup = [
                f"        <key><fifths>{fifths}</fifths><mode>{mode}</mode></key>",
                f"        <time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>",
                "        <staves>2</staves>",
                '        <clef number="1"><sign>G</sign><line>2</line></clef>',
                '        <clef number="2"><sign>F</sign><line>4</line></clef>',
            ]
            m_lines[insert_at:insert_at] = setup
            m_lines.insert(insert_at + len(setup) + 1, '      <sound tempo="110"/>')
            first_measure = False
        xml.extend(m_lines)

    xml.append("  </part>")
    xml.append("</score-partwise>")
    out.write_text("\n".join(xml) + "\n", encoding="utf-8")
    return out, flagged


def main():
    bars, beats, beat_type = parse_master()
    print(f"Parsed {len(bars)} measures from master.")

    all_flagged = {}
    for mode, key_list in (("major", MAJOR_KEYS), ("minor", MINOR_KEYS)):
        for label, tonic_letter, sharps, flats in key_list:
            shift = LETTER_INDEX[tonic_letter]
            fifths = sharps if sharps else -flats
            target_scale = key_scale(sharps, flats)
            out, flagged = write_key_file(label, mode, fifths, bars, beats, beat_type, shift, target_scale)
            tag = f" *** still out of range: measures {flagged}" if flagged else ""
            print(f"Wrote {out.name}{tag}")
            if flagged:
                all_flagged[label] = flagged

    if all_flagged:
        print("\nNeeds manual octave correction (motif spans >1 octave beyond the F2/C6 cap):")
        for label, ms in all_flagged.items():
            print(f"  {label}: measures {ms}")


if __name__ == "__main__":
    main()
