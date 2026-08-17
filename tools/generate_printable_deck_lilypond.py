#!/usr/bin/env python3
"""Generate a printable SVG sheet for the current deck using LilyPond snippets."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import textwrap
from pathlib import Path
import xml.etree.ElementTree as ET

NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)

PAGE_WIDTH = 816
PAGE_HEIGHT = 1056
MARGIN = 24
GUTTER = 12
ROWS = 4
CARD_HEIGHT = (PAGE_HEIGHT - 2 * MARGIN - (ROWS - 1) * GUTTER) / ROWS
STANDARD_CARD_ASPECT_RATIO = 2.5 / 3.5
CARD_WIDTH = CARD_HEIGHT * STANDARD_CARD_ASPECT_RATIO
COLS = 4
PAGE_X_OFFSET = (PAGE_WIDTH - (COLS * CARD_WIDTH + (COLS - 1) * GUTTER)) / 2

MUSIC_BOX_X = 2
MUSIC_BOX_Y = 74
MUSIC_BOX_WIDTH = CARD_WIDTH - 4
MUSIC_BOX_HEIGHT = 128

FAMILY_COLOR = {
    "C major": "#e34a4a",
    "F major": "#f39c34",
    "G major": "#2eae5f",
    "D minor": "#4d79ff",
}
FAMILY_ABBREV = {
    "C major": "C",
    "F major": "F",
    "G major": "G",
    "D minor": "Dm",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a printable SVG deck sheet with LilyPond.")
    parser.add_argument("--input", type=Path, default=Path("data/starter-deck.json"))
    parser.add_argument("--output", type=Path, default=Path("data/printable-deck-sheet.svg"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/lilypond-cache"))
    parser.add_argument("--lilypond-bin", type=str, default="lilypond")
    return parser.parse_args()


def svg(tag: str, **attrs: str) -> ET.Element:
    return ET.Element(f"{{{NS}}}{tag}", attrs)


def sub(parent: ET.Element, tag: str, text: str | None = None, class_: str | None = None, **attrs: str) -> ET.Element:
    if class_ is not None:
        attrs["class"] = class_
    element = ET.SubElement(parent, f"{{{NS}}}{tag}", attrs)
    if text is not None:
        element.text = text
    return element


def add_text(card: ET.Element, x: float, y: float, text: str, cls: str, anchor: str = "start", size: int = 10) -> None:
    sub(
        card,
        "text",
        text,
        x=f"{x}",
        y=f"{y}",
        class_=cls,
        **{"text-anchor": anchor, "font-size": str(size)},
    )


def wrap_text(text: str, max_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return [text]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def lilypond_pitch(note: dict[str, object]) -> str:
    step = str(note["step"]).lower()
    alter = int(note.get("alter", 0))
    accidental = "is" * alter if alter > 0 else "es" * (-alter)
    octave = int(note["octave"])
    if octave >= 3:
        suffix = "'" * (octave - 3)
    else:
        suffix = "," * (3 - octave)
    return f"{step}{accidental}{suffix}"


def lilypond_music(card: dict[str, object]) -> str:
    token_type = int(card["tokenType"])
    notes = card.get("notes", [])

    if token_type == 0:
        return "r4"
    if token_type in (1, 2, 3):
        return f"{lilypond_pitch(notes[0])}4"
    if token_type in (4, 5, 6):
        return " ".join(f"{lilypond_pitch(note)}8" for note in notes[:2])
    if token_type in (7, 8):
        return " ".join(f"{lilypond_pitch(note)}16" for note in notes[:4])
    if token_type == 9:
        triplet_notes = " ".join(f"{lilypond_pitch(note)}8" for note in notes[:3])
        return f"\\tuplet 3/2 {{ {triplet_notes} }}"
    return "r4"


def lilypond_source(card: dict[str, object]) -> str:
    music = lilypond_music(card)
    return textwrap.dedent(
        f"""\
        \\version "2.24.0"
        #(set-global-staff-size 200)

        \\paper {{
          #(set-paper-size "a6")
          top-margin = 0
          bottom-margin = 0
          left-margin = 0
          right-margin = 0
          indent = 0
          tagline = ##f
          print-page-number = ##f
          line-width = 100\\mm
        }}

        \\layout {{
          ragged-right = ##f
          \\context {{
            \\Score
            \\omit BarNumber
            \\override SpacingSpanner.uniform-stretching = ##t
          }}
          \\context {{
            \\Staff
            \\omit Clef
            \\omit TimeSignature
            \\omit KeySignature
            \\omit BarLine
          }}
        }}

        \\score {{
          \\new Staff \\with {{
            \\omit Clef
            \\omit TimeSignature
            \\omit KeySignature
            \\omit BarLine
          }} {{
            \\time 4/4
            s4 {music} s2
          }}
        }}
        """
    )


def render_lilypond_svg(card: dict[str, object], cache_dir: Path, lilypond_bin: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    stem = card["id"].lower().replace("-", "_")
    ly_path = cache_dir / f"{stem}.ly"
    svg_path = cache_dir / f"{stem}.svg"
    ly_path.write_text(lilypond_source(card), encoding="utf-8")

    if not shutil.which(lilypond_bin):
        raise FileNotFoundError(
            f"Could not find '{lilypond_bin}'. Install LilyPond, then rerun this generator."
        )

    if not svg_path.exists() or svg_path.stat().st_mtime < ly_path.stat().st_mtime:
        subprocess.run(
            [
                lilypond_bin,
                "-dbackend=svg",
                "-dno-point-and-click",
                "-dclip-systems",
                "-o",
                stem,
                ly_path.name,
            ],
            cwd=cache_dir,
            check=True,
            capture_output=True,
            text=True,
        )

    return svg_path


def embed_svg(svg_path: Path, x: float, y: float, width: float, height: float) -> ET.Element:
    source_root = ET.parse(svg_path).getroot()
    attrs: dict[str, str] = {
        "x": f"{x}",
        "y": f"{y}",
        "width": f"{width}",
        "height": f"{height}",
        "preserveAspectRatio": "xMidYMid meet",
    }
    if "viewBox" in source_root.attrib:
        attrs["viewBox"] = source_root.attrib["viewBox"]
    embedded = svg("svg", **attrs)
    for child in list(source_root):
        embedded.append(child)
    return embedded


def render_card(card: dict[str, object], page_x: float, page_y: float, col: int, row: int, cache_dir: Path, lilypond_bin: str) -> ET.Element:
    x = page_x + PAGE_X_OFFSET + col * (CARD_WIDTH + GUTTER)
    y = page_y + MARGIN + row * (CARD_HEIGHT + GUTTER)

    group = svg("g", transform=f"translate({x},{y})")
    sub(group, "rect", x="0", y="0", width=f"{CARD_WIDTH}", height=f"{CARD_HEIGHT}", rx="14", ry="14", class_="card-border")

    family = str(card["primaryFamily"])
    badge_w = 58 if family != "D minor" else 66
    badge_x = CARD_WIDTH - badge_w - 12
    badge = sub(group, "g", transform=f"translate({badge_x},12)")
    sub(badge, "rect", x="0", y="0", width=f"{badge_w}", height="22", rx="11", ry="11", fill=FAMILY_COLOR[family], class_="badge")
    add_text(badge, badge_w / 2, 15.5, FAMILY_ABBREV[family], "badge-text", anchor="middle", size=12)

    title = f"{card['id']} · {card['rhythm']}"
    title_max_chars = max(12, int((CARD_WIDTH - 18) / 6.6))
    title_lines = wrap_text(title, title_max_chars)
    for idx, line in enumerate(title_lines[:4]):
        add_text(group, 12, 22 + idx * 11, line, "card-title", size=11)

    compatible = "/".join(FAMILY_ABBREV[f] for f in card["familyCompatibility"])
    add_text(group, 12, 48, f"fits: {compatible}", "compat-text", size=9)

    music_svg = render_lilypond_svg(card, cache_dir, lilypond_bin)
    group.append(embed_svg(music_svg, MUSIC_BOX_X, MUSIC_BOX_Y, MUSIC_BOX_WIDTH, MUSIC_BOX_HEIGHT))

    primary_fit = float(card.get("familyFit", {}).get(family, 0.0))
    add_text(group, 12, CARD_HEIGHT - 12, f"fit {primary_fit:.2f}", "tiny-text", size=8)
    add_text(group, CARD_WIDTH - 12, CARD_HEIGHT - 12, "LilyPond", "tiny-text", anchor="end", size=8)
    return group


def build_document(deck: dict[str, object], cache_dir: Path, lilypond_bin: str) -> ET.Element:
    cards = list(deck["cards"])
    pages = -(-len(cards) // (COLS * ROWS))
    root = svg(
        "svg",
        width="8.5in",
        height=f"{pages * 11}in",
        viewBox=f"0 0 {PAGE_WIDTH} {pages * PAGE_HEIGHT}",
        version="1.1",
    )

    style = sub(root, "style")
    style.text = """
      .page-bg { fill: #ffffff; }
      .page-guide { fill: none; stroke: #e0e0e0; stroke-width: 1; }
      .card-border { fill: #fffdf9; stroke: #222; stroke-width: 1.1; }
      .badge-text { fill: #fff; font-family: Arial, sans-serif; font-weight: 700; }
      .card-title { fill: #111; font-family: Arial, sans-serif; font-weight: 700; }
      .compat-text { fill: #444; font-family: Arial, sans-serif; }
      .tiny-text { fill: #555; font-family: Arial, sans-serif; }
    """

    for page_index in range(pages):
        page_y = page_index * PAGE_HEIGHT
        sub(root, "rect", x="0", y=f"{page_y}", width=f"{PAGE_WIDTH}", height=f"{PAGE_HEIGHT}", class_="page-bg")
        sub(root, "rect", x="0", y=f"{page_y}", width=f"{PAGE_WIDTH}", height=f"{PAGE_HEIGHT}", class_="page-guide")
        add_text(root, 28, page_y + 22, f"Page {page_index + 1}", "tiny-text", size=10)

        for slot in range(COLS * ROWS):
            card_index = page_index * COLS * ROWS + slot
            if card_index >= len(cards):
                break
            card = cards[card_index]
            row, col = divmod(slot, COLS)
            root.append(render_card(card, 0, page_y, col, row, cache_dir, lilypond_bin))

    return root


def main() -> None:
    args = parse_args()
    deck = json.loads(args.input.read_text(encoding="utf-8"))
    root = build_document(deck, args.cache_dir, args.lilypond_bin)
    ET.indent(root, space="  ")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(args.output, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
