#!/usr/bin/env python3
"""Generate printable chord-family cards for the phrase deck."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from generate_printable_deck_lilypond import (
    CARD_HEIGHT,
    CARD_WIDTH,
    COLS,
    FAMILY_COLOR,
    GUTTER,
    MARGIN,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    PAGE_X_OFFSET,
    ROWS,
    convert_svg_to_pdf,
    normalize_output_formats,
    sub,
    svg,
)

NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)

FAMILIES = ("C major", "F major", "G major", "D minor")
COPIES_PER_FAMILY = 8


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate printable chord-family cards.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/chord-family-cards-pages"))
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["both"],
        help="Output formats to generate: svg, pdf, or both (default).",
    )
    return parser.parse_args()


def build_cards() -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []
    for copy_index in range(COPIES_PER_FAMILY):
        for family in FAMILIES:
            slug = family.replace(" ", "-").lower()
            cards.append(
                {
                    "id": f"{slug}-{copy_index + 1:02d}",
                    "family": family,
                    "copyIndex": copy_index + 1,
                    "label": family,
                }
            )
    return cards


def render_family_card(card: dict[str, object], page_x: float, page_y: float, col: int, row: int) -> ET.Element:
    family = str(card["family"])
    x = page_x + PAGE_X_OFFSET + col * (CARD_WIDTH + GUTTER)
    y = page_y + MARGIN + row * (CARD_HEIGHT + GUTTER)

    group = svg("g", transform=f"translate({x},{y})")
    sub(
        group,
        "rect",
        x="0",
        y="0",
        width=f"{CARD_WIDTH}",
        height=f"{CARD_HEIGHT}",
        rx="14",
        ry="14",
        fill=FAMILY_COLOR[family],
        stroke="#ffffff",
        **{"stroke-width": "1.5"},
    )

    font_size = 30 if len(family) <= 8 else 28
    sub(
        group,
        "text",
        family,
        x=f"{CARD_WIDTH / 2}",
        y=f"{CARD_HEIGHT / 2 + 12}",
        fill="#ffffff",
        **{
            "font-family": "Arial, sans-serif",
            "font-size": str(font_size),
            "font-weight": "700",
            "text-anchor": "middle",
            "dominant-baseline": "middle",
        },
    )

    return group


def build_page_document(cards: list[dict[str, object]], page_index: int, page_count: int) -> ET.Element:
    root = svg(
        "svg",
        width="8.5in",
        height="11in",
        viewBox=f"0 0 {PAGE_WIDTH} {PAGE_HEIGHT}",
        version="1.1",
    )

    style = sub(root, "style")
    style.text = """
      .page-bg { fill: #ffffff; }
      .page-guide { fill: none; stroke: #e0e0e0; stroke-width: 1; }
      .cut-guide { fill: none; stroke: #9a9a9a; stroke-width: 0.8; stroke-dasharray: 4 4; }
      .page-meta { fill: #666; font-family: Arial, sans-serif; font-size: 10px; font-weight: 600; }
    """

    sub(root, "rect", x="0", y="0", width=f"{PAGE_WIDTH}", height=f"{PAGE_HEIGHT}", class_="page-bg")
    sub(root, "rect", x="0", y="0", width=f"{PAGE_WIDTH}", height=f"{PAGE_HEIGHT}", class_="page-guide")

    half_gutter = GUTTER / 2
    cut_x0 = PAGE_X_OFFSET - half_gutter
    cut_y0 = MARGIN - half_gutter
    cut_x1 = PAGE_X_OFFSET + COLS * CARD_WIDTH + (COLS - 1) * GUTTER + half_gutter
    cut_y1 = MARGIN + ROWS * CARD_HEIGHT + (ROWS - 1) * GUTTER + half_gutter
    sub(root, "line", x1=f"{cut_x0}", y1=f"{cut_y0}", x2=f"{cut_x1}", y2=f"{cut_y0}", class_="cut-guide")
    sub(root, "line", x1=f"{cut_x0}", y1=f"{cut_y1}", x2=f"{cut_x1}", y2=f"{cut_y1}", class_="cut-guide")
    sub(root, "line", x1=f"{cut_x0}", y1=f"{cut_y0}", x2=f"{cut_x0}", y2=f"{cut_y1}", class_="cut-guide")
    sub(root, "line", x1=f"{cut_x1}", y1=f"{cut_y0}", x2=f"{cut_x1}", y2=f"{cut_y1}", class_="cut-guide")
    for col in range(1, COLS):
        x = PAGE_X_OFFSET + col * CARD_WIDTH + (col - 0.5) * GUTTER
        sub(root, "line", x1=f"{x}", y1=f"{cut_y0}", x2=f"{x}", y2=f"{cut_y1}", class_="cut-guide")
    for row in range(1, ROWS):
        y = MARGIN + row * CARD_HEIGHT + (row - 0.5) * GUTTER
        sub(root, "line", x1=f"{cut_x0}", y1=f"{y}", x2=f"{cut_x1}", y2=f"{y}", class_="cut-guide")

    sub(
        root,
        "text",
        f"{page_index + 1} of {page_count}",
        x=f"{PAGE_WIDTH / 2}",
        y="12",
        **{"fill": "#666", "font-family": "Arial, sans-serif", "font-size": "10", "font-weight": "600", "text-anchor": "middle"},
    )

    for slot in range(COLS * ROWS):
        card_index = page_index * COLS * ROWS + slot
        if card_index >= len(cards):
            break
        row, col = divmod(slot, COLS)
        root.append(render_family_card(cards[card_index], 0, 0, col, row))

    return root


def main() -> None:
    args = parse_args()
    formats = normalize_output_formats(args.formats)
    cards = build_cards()
    pages = math.ceil(len(cards) / (COLS * ROWS))
    args.output_dir.mkdir(parents=True, exist_ok=True)

    svg_paths: list[Path] = []
    for page_index in range(pages):
        root = build_page_document(cards, page_index, pages)
        ET.indent(root, space="  ")
        output_path = args.output_dir / f"chord-family-cards-page-{page_index + 1:02d}.svg"
        ET.ElementTree(root).write(output_path, encoding="utf-8", xml_declaration=True)
        svg_paths.append(output_path)
        if "svg" in formats:
            print(f"Wrote {output_path}")

    if "pdf" in formats:
        pdf_dir = args.output_dir / "pdf"
        for svg_path in svg_paths:
            pdf_path = pdf_dir / svg_path.name.replace(".svg", ".pdf")
            convert_svg_to_pdf(svg_path, pdf_path)
            print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
