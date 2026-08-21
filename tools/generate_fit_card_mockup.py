#!/usr/bin/env python3
"""Render one existing deck card with compact fit boxes below its staff."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from generate_printable_deck_lilypond import (
    CARD_HEIGHT,
    CARD_WIDTH,
    FAMILY_ABBREV,
    FAMILY_COLOR,
    add_text,
    embed_svg,
    render_lilypond_svg,
    sub,
    svg,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a compact fit-card layout mockup.")
    parser.add_argument("--card-id", default="C-0010")
    parser.add_argument("--input", type=Path, default=Path("data/starter-deck.json"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/lilypond-cache"))
    parser.add_argument("--output", type=Path, default=Path("data/fit-card-layout-mockup.svg"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    deck = json.loads(args.input.read_text(encoding="utf-8"))
    card = next(card for card in deck["cards"] if card["id"] == args.card_id)
    compatible_families = list(card["familyCompatibility"])
    family_fit = card["familyFit"]
    compatible_families.sort(key=lambda family_name: family_fit[family_name], reverse=True)

    root = svg(
        "svg",
        width="2.5in",
        height="3.5in",
        viewBox=f"0 0 {CARD_WIDTH} {CARD_HEIGHT}",
        version="1.1",
    )
    style = sub(root, "style")
    style.text = """
      .card-border { fill: #fffdf9; stroke: #222; stroke-width: 1.1; }
      .badge-text { fill: #fff; font-family: Arial, sans-serif; font-weight: 700; }
      .card-title { fill: #111; font-family: Arial, sans-serif; font-weight: 700; }
      .fit-text { fill: #fff; font-family: Arial, sans-serif; font-weight: 700; }
    .card-id-hidden { display: none; }
    """

    group = svg("g")
    root.append(group)
    sub(group, "rect", x="0", y="0", width=f"{CARD_WIDTH}", height=f"{CARD_HEIGHT}", rx="14", ry="14", class_="card-border")

    music_svg = render_lilypond_svg(card, args.cache_dir, "lilypond")
    group.append(embed_svg(music_svg, 0, 44, CARD_WIDTH, 100))

    box_gap = 3
    box_x = 8
    box_y = 145
    box_h = 23
    box_w = CARD_WIDTH - 2 * box_x
    for index, family_name in enumerate(compatible_families):
        y = box_y + index * (box_h + box_gap)
        sub(group, "rect", x=f"{box_x}", y=f"{y}", width=f"{box_w}", height=f"{box_h}", rx="4", ry="4", fill=FAMILY_COLOR[family_name])
        fit = family_fit[family_name]
        points = 3 if fit >= 0.8 else 2 if fit >= 0.55 else 1
        label = f"{FAMILY_ABBREV[family_name]}  {points} pt"
        add_text(group, box_x + 10, y + 15, label, "fit-text", size=10)

    add_text(group, 12, CARD_HEIGHT - 12, card["id"], "card-id-hidden", size=11)
    ET.indent(root, space="  ")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(args.output, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()