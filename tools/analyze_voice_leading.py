#!/usr/bin/env python3
"""Classify each bar's treble-voice contour as rising/falling/neither and log
the distribution.

Rule: compare the first and last sounding (non-rest) note of the bar's treble
voice. If they are more than a major 3rd apart (> 4 semitones), the bar is
"rising" (last higher) or "falling" (last lower); otherwise "neither".

Run: python3 tools/analyze_voice_leading.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BARS_JSON = ROOT / "data" / "merged_bars.json"
OUT_PATH = ROOT / "analysis" / "voice_leading_merged.log"

STEP_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
MAJOR_THIRD_SEMITONES = 4


def midi(note):
    return (note["octave"] + 1) * 12 + STEP_SEMITONES[note["step"]] + note.get("alter", 0)


def classify(events):
    notes = [e for e in events if e["type"] == "note"]
    if not notes:
        return "neither", None, None
    first_midi, last_midi = midi(notes[0]), midi(notes[-1])
    diff = last_midi - first_midi
    if diff > MAJOR_THIRD_SEMITONES:
        return "rising", first_midi, last_midi
    if diff < -MAJOR_THIRD_SEMITONES:
        return "falling", first_midi, last_midi
    return "neither", first_midi, last_midi


def main():
    bars_path = Path(sys.argv[1]) if len(sys.argv) > 1 else BARS_JSON
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT_PATH
    data = json.loads(bars_path.read_text(encoding="utf-8"))
    bars = data["bars"]

    overall = Counter()
    by_chord = {}
    per_bar = []

    for bar in bars:
        result, first_midi, last_midi = classify(bar["treble"])
        overall[result] += 1
        by_chord.setdefault(bar["chord"], Counter())[result] += 1
        per_bar.append((bar["measure"], bar["chord"], result, first_midi, last_midi))

    total = len(bars)
    lines = []
    lines.append("Voice-leading contour analysis (treble voice)")
    lines.append("Rule: rising/falling if first and last sounding note differ by more than a")
    lines.append("major 3rd (4 semitones); otherwise neither.")
    lines.append(f"Bars analyzed: {total}")
    lines.append("")
    lines.append("Overall distribution:")
    for label in ("rising", "falling", "neither"):
        count = overall[label]
        pct = 100 * count / total
        lines.append(f"  {label:8s} {count:4d}  ({pct:5.1f}%)")
    lines.append("")
    lines.append("By chord:")
    seen_chords = []
    for chord in data["chordOrder"]:
        if chord in seen_chords:
            continue
        seen_chords.append(chord)
        counts = by_chord.get(chord, Counter())
        chord_total = sum(counts.values())
        parts = ", ".join(f"{label}={counts[label]}" for label in ("rising", "falling", "neither"))
        lines.append(f"  {chord:8s} (n={chord_total:3d}): {parts}")
    lines.append("")
    lines.append("Per-bar detail (measure, chord, contour, first->last MIDI):")
    for measure, chord, result, first_midi, last_midi in per_bar:
        lines.append(f"  {measure:4d}  {chord:8s} {result:8s} {first_midi}->{last_midi}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote voice-leading analysis for {total} bars to {out_path}")


if __name__ == "__main__":
    main()
