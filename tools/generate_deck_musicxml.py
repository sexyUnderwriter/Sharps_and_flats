#!/usr/bin/env python3
"""Generate a MusicXML view of the game deck.

This script is intentionally reproducible: the deck JSON is the source of truth,
and the MusicXML output is generated from it each time we tune the tokens.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

FAMILY_ORDER = ["C major", "F major", "G major", "D minor"]
COLOR_MAP = {
    "C major": {"red": "255", "green": "0", "blue": "0"},
    "F major": {"red": "255", "green": "128", "blue": "0"},
    "G major": {"red": "0", "green": "153", "blue": "0"},
    "D minor": {"red": "0", "green": "0", "blue": "255"},
}
KEY_MAP = {
    "C major": "0",
    "F major": "-1",
    "G major": "1",
    "D minor": "-1",
}
MODE_MAP = {
    "C major": "major",
    "F major": "major",
    "G major": "major",
    "D minor": "minor",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate MusicXML deck visualizations from a JSON deck file.")
    parser.add_argument("--input", type=Path, default=Path("data/starter-deck.json"), help="Path to the deck JSON file.")
    parser.add_argument("--output", type=Path, default=Path("data/starter-deck.musicxml"), help="Path to write the MusicXML file.")
    return parser.parse_args()


def add_color(el: ET.Element, family: str) -> None:
    rgb = COLOR_MAP[family]
    color_hex = f"#{int(rgb['red']):02X}{int(rgb['green']):02X}{int(rgb['blue']):02X}"
    el.set("color", color_hex)


def note_to_pitch(note: dict) -> ET.Element:
    pitch = ET.Element("pitch")
    ET.SubElement(pitch, "step").text = note["step"]
    alter = note.get("alter", 0)
    if alter != 0:
        ET.SubElement(pitch, "alter").text = str(alter)
    ET.SubElement(pitch, "octave").text = str(note["octave"])
    return pitch


def token_payload(card: dict) -> list[dict]:
    token_type = card["tokenType"]
    notes = card.get("notes", [])

    if token_type == 0:
        return [{"kind": "rest", "duration": 960, "type": "quarter"}]

    if token_type in (1, 2, 3):
        note = notes[0]
        return [{"kind": "pitch", "note": note, "duration": 960, "type": "quarter"}]

    if token_type in (4, 5, 6):
        return [
            {"kind": "pitch", "note": n, "duration": 480, "type": "eighth"}
            for n in notes[:2]
        ]

    if token_type in (7, 8):
        return [
            {"kind": "pitch", "note": n, "duration": 240, "type": "16th"}
            for n in notes[:4]
        ]

    if token_type == 9:
        return [
            {"kind": "pitch", "note": n, "duration": 320, "type": "eighth"}
            for n in notes[:3]
        ]

    return [{"kind": "rest", "duration": 960, "type": "quarter"}]


def render_card_measure(card: dict, measure_number: int) -> ET.Element:
    family = card["primaryFamily"]
    measure = ET.Element("measure", {"number": str(measure_number)})

    attrs = ET.SubElement(measure, "attributes")
    ET.SubElement(attrs, "divisions").text = "960"
    key = ET.SubElement(attrs, "key")
    ET.SubElement(key, "fifths").text = KEY_MAP[family]
    ET.SubElement(key, "mode").text = MODE_MAP[family]
    time = ET.SubElement(attrs, "time")
    ET.SubElement(time, "beats").text = "1"
    ET.SubElement(time, "beat-type").text = "4"
    clef = ET.SubElement(attrs, "clef")
    ET.SubElement(clef, "sign").text = "G"
    ET.SubElement(clef, "line").text = "2"

    direction = ET.SubElement(measure, "direction", {"placement": "above"})
    direction_type = ET.SubElement(direction, "direction-type")
    compatible_families = "/".join(card["familyCompatibility"])
    ET.SubElement(direction_type, "words").text = (
        f"{card['id']} | {card['rhythm']} | compatible: {compatible_families}"
    )

    payload = token_payload(card)
    for item_index, item in enumerate(payload):
        note_el = ET.SubElement(measure, "note")
        if item["kind"] == "rest":
            ET.SubElement(note_el, "rest")
        else:
            note = item["note"]
            note_el.append(note_to_pitch(note))
        ET.SubElement(note_el, "duration").text = str(item["duration"])
        ET.SubElement(note_el, "voice").text = "1"
        ET.SubElement(note_el, "type").text = item["type"]
        if item["kind"] == "pitch":
            alter = item["note"].get("alter", 0)
            if alter != 0:
                ET.SubElement(note_el, "accidental").text = "sharp" if alter > 0 else "flat"
        if card["tokenType"] == 9:
            time_modification = ET.SubElement(note_el, "time-modification")
            ET.SubElement(time_modification, "actual-notes").text = "3"
            ET.SubElement(time_modification, "normal-notes").text = "2"
        beam_count = 2 if card["tokenType"] in (7, 8) else 1 if card["tokenType"] in (4, 5, 6, 9) else 0
        if beam_count:
            if item_index == 0:
                beam_value = "begin"
            elif item_index == len(payload) - 1:
                beam_value = "end"
            else:
                beam_value = "continue"
            for beam_number in range(1, beam_count + 1):
                ET.SubElement(note_el, "beam", {"number": str(beam_number)}).text = beam_value
        if card["tokenType"] == 9 and item_index in (0, len(payload) - 1):
            notations = ET.SubElement(note_el, "notations")
            if item_index == 0:
                ET.SubElement(
                    notations,
                    "tuplet",
                    {
                        "type": "start",
                        "placement": "above",
                        "bracket": "no",
                        "show-number": "actual",
                    },
                )
            else:
                ET.SubElement(notations, "tuplet", {"type": "stop"})
        add_color(note_el, family)

    ET.SubElement(measure, "barline", {"location": "right"})
    return measure


def build_musicxml(deck: dict) -> ET.Element:
    root = ET.Element("score-partwise", {"version": "3.1"})
    work = ET.SubElement(root, "work")
    ET.SubElement(work, "work-title").text = deck["deck"].get("name", "Deck Tokens")
    identification = ET.SubElement(root, "identification")
    encoding = ET.SubElement(identification, "encoding")
    ET.SubElement(
        encoding,
        "supports",
        {"element": "note", "attribute": "color", "type": "yes"},
    )

    part_list = ET.SubElement(root, "part-list")
    score_part = ET.SubElement(part_list, "score-part", {"id": "P1"})
    ET.SubElement(score_part, "part-name").text = "Tokens"

    part = ET.SubElement(root, "part", {"id": "P1"})

    ordered_cards = []
    added_ids = set()
    for family in FAMILY_ORDER:
        for card in deck["cards"]:
            if card.get("primaryFamily") == family and card["id"] not in added_ids:
                ordered_cards.append(card)
                added_ids.add(card["id"])

    for measure_number, card in enumerate(ordered_cards, start=1):
        part.append(render_card_measure(card, measure_number))

    return root


def main() -> None:
    args = parse_args()
    with args.input.open("r", encoding="utf-8") as f:
        deck = json.load(f)

    root = build_musicxml(deck)
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(args.output, encoding="utf-8", xml_declaration=True)
    print(f"Generated {args.output} with {len(deck['cards'])} cards")


if __name__ == "__main__":
    main()
