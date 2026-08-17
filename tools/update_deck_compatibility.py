#!/usr/bin/env python3
"""Compute multi-family legality and tonal fit for every deck card."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FAMILY_ORDER = ("C major", "F major", "G major", "D minor")
STEP_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
FAMILY_SCALES = {
    "C major": {0, 2, 4, 5, 7, 9, 11},
    "F major": {0, 2, 4, 5, 7, 9, 10},
    "G major": {0, 2, 4, 6, 7, 9, 11},
    "D minor": {0, 1, 2, 4, 5, 7, 9, 10},
}
FAMILY_CHORDS = {
    "C major": {0, 4, 7},
    "F major": {0, 5, 9},
    "G major": {2, 7, 11},
    "D minor": {2, 5, 9},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update deck cards with computed tonal compatibility.")
    parser.add_argument("--input", type=Path, default=Path("data/starter-deck.json"))
    parser.add_argument("--output", type=Path, default=Path("data/starter-deck.json"))
    return parser.parse_args()


def note_pitch_class(note: dict[str, Any]) -> int:
    return (STEP_PITCH_CLASS[note["step"]] + int(note.get("alter", 0))) % 12


def analyze_card(card: dict[str, Any]) -> tuple[list[str], dict[str, float]]:
    primary_family = card.get("primaryFamily") or card["familyCompatibility"][0]
    if card.get("isRest", False):
        compatibility = list(FAMILY_ORDER)
        return compatibility, {
            family: 0.65 + (0.05 if family == primary_family else 0.0)
            for family in compatibility
        }

    pitch_classes = [note_pitch_class(note) for note in card.get("notes", [])]
    pitch_class_set = set(pitch_classes)
    compatibility = [
        family
        for family in FAMILY_ORDER
        if pitch_class_set <= FAMILY_SCALES[family]
    ]
    if primary_family not in compatibility:
        raise ValueError(f"{card['id']} is not pitch-compatible with its primary family {primary_family}.")

    family_fit = {}
    for family in compatibility:
        chord = FAMILY_CHORDS[family]
        chord_tone_ratio = sum(pitch_class in chord for pitch_class in pitch_classes) / len(pitch_classes)
        fit = (
            0.35
            + 0.35 * chord_tone_ratio
            + 0.10 * (pitch_classes[0] in chord)
            + 0.15 * (pitch_classes[-1] in chord)
            + 0.05 * (family == primary_family)
        )
        family_fit[family] = round(min(1.0, fit), 3)
    return compatibility, family_fit


def update_deck(deck: dict[str, Any]) -> dict[str, Any]:
    for card in deck["cards"]:
        primary_family = card.get("primaryFamily") or card["familyCompatibility"][0]
        compatibility, family_fit = analyze_card(card)
        card["primaryFamily"] = primary_family
        card["familyCompatibility"] = compatibility
        card["familyFit"] = family_fit
    return deck


def main() -> None:
    args = parse_args()
    deck = json.loads(args.input.read_text(encoding="utf-8"))
    updated_deck = update_deck(deck)
    args.output.write_text(json.dumps(updated_deck, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {len(updated_deck['cards'])} cards in {args.output}")


if __name__ == "__main__":
    main()
