#!/usr/bin/env python3
"""Generate printable per-page SVG sheets for the current deck using LilyPond snippets."""

from __future__ import annotations

import argparse
import json
import re
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

MUSIC_BOX_X = 0
MUSIC_BOX_Y = 56
MUSIC_BOX_WIDTH = CARD_WIDTH
MUSIC_BOX_HEIGHT = 154

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
SVG_CANVAS_SCALE = 1.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate printable per-page SVG deck sheets with LilyPond.")
    parser.add_argument("--input", type=Path, default=Path("data/starter-deck.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/printable-deck-pages"))
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


def parse_dimension(value: str) -> tuple[float, str]:
    if value.endswith("mm"):
        return float(value[:-2]), "mm"
    return float(value), ""


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
          line-width = 90\\mm
        }}

        \\layout {{
          ragged-right = ##f
          \\context {{
            \\Score
            \\omit BarNumber
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


def extract_staff_top_y(svg_path: Path) -> float:
    root = ET.parse(svg_path).getroot()
    return extract_staff_top_y_from_root(root)


def normalize_staff_position(root: ET.Element, target_top_y: float) -> None:
    staff_top_y = extract_staff_top_y_from_root(root)
    delta_y = target_top_y - staff_top_y
    if abs(delta_y) < 1e-9:
        return

    style_nodes = [child for child in list(root) if child.tag == f"{{{NS}}}style"]
    drawing_nodes = [child for child in list(root) if child.tag != f"{{{NS}}}style"]
    for child in drawing_nodes:
        root.remove(child)

    wrapped = svg("g", transform=f"translate(0,{delta_y:.4f})")
    for child in drawing_nodes:
        wrapped.append(child)
    for style in style_nodes:
        root.append(style)
    root.append(wrapped)


def extract_staff_top_y_from_root(root: ET.Element) -> float:
    staff_y_values: list[float] = []
    for element in root.iter():
        if element.tag != f"{{{NS}}}g":
            continue
        if not any(child.tag == f"{{{NS}}}line" for child in list(element)):
            continue
        transform = element.attrib.get("transform", "")
        match = re.search(r"translate\(\s*([^,\s]+)\s*,\s*([^\)]+)\s*\)", transform)
        if match is None:
            continue
        _, y_value = match.groups()
        staff_y_values.append(float(y_value))
    if not staff_y_values:
        return 0.0
    return max(staff_y_values)


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
                "-o",
                stem,
                ly_path.name,
            ],
            cwd=cache_dir,
            check=True,
            capture_output=True,
            text=True,
        )

    root = ET.parse(svg_path).getroot()
    reference_svg = cache_dir / "f_0012.svg"
    target_top_y = extract_staff_top_y(reference_svg) if reference_svg.exists() else 6.8831
    normalize_staff_position(root, target_top_y)

    width = root.attrib.get("width")
    height = root.attrib.get("height")
    view_box = root.attrib.get("viewBox")
    if width and height and view_box:
        width_value, width_unit = parse_dimension(width)
        height_value, height_unit = parse_dimension(height)
        view_x, view_y, view_w, view_h = map(float, view_box.split())
        root.attrib["width"] = f"{width_value * SVG_CANVAS_SCALE:.2f}{width_unit}"
        root.attrib["height"] = f"{height_value * SVG_CANVAS_SCALE:.2f}{height_unit}"
        root.attrib["viewBox"] = f"{view_x:.4f} {view_y:.4f} {view_w * SVG_CANVAS_SCALE:.4f} {view_h * SVG_CANVAS_SCALE:.4f}"
        ET.ElementTree(root).write(svg_path, encoding="utf-8", xml_declaration=False)

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

    compatible_families = list(card["familyCompatibility"])
    badge_gap = 5
    badge_h = 20
    badge_w = 28
    total_badge_w = len(compatible_families) * badge_w + max(0, len(compatible_families) - 1) * badge_gap
    badge_x = CARD_WIDTH - total_badge_w - 12
    badge_row = sub(group, "g", transform=f"translate({badge_x},12)")
    for index, family_name in enumerate(compatible_families):
        badge = sub(badge_row, "g", transform=f"translate({index * (badge_w + badge_gap)},0)")
        sub(badge, "rect", x="0", y="0", width=f"{badge_w}", height=f"{badge_h}", rx="10", ry="10", fill=FAMILY_COLOR[family_name], class_="badge")
        add_text(badge, badge_w / 2, 14.0, FAMILY_ABBREV[family_name], "badge-text", anchor="middle", size=10)

    add_text(group, 12, CARD_HEIGHT - 12, str(card["id"]), "card-title", size=11)

    music_svg = render_lilypond_svg(card, cache_dir, lilypond_bin)
    group.append(embed_svg(music_svg, MUSIC_BOX_X, MUSIC_BOX_Y, MUSIC_BOX_WIDTH, MUSIC_BOX_HEIGHT))
    return group


def build_page_document(deck: dict[str, object], page_index: int, cache_dir: Path, lilypond_bin: str) -> ET.Element:
    cards = list(deck["cards"])
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
      .card-border { fill: #fffdf9; stroke: #222; stroke-width: 1.1; }
      .badge-text { fill: #fff; font-family: Arial, sans-serif; font-weight: 700; }
      .card-title { fill: #111; font-family: Arial, sans-serif; font-weight: 700; }
      .compat-text { fill: #444; font-family: Arial, sans-serif; }
      .tiny-text { fill: #555; font-family: Arial, sans-serif; }
    """

    sub(root, "rect", x="0", y="0", width=f"{PAGE_WIDTH}", height=f"{PAGE_HEIGHT}", class_="page-bg")
    sub(root, "rect", x="0", y="0", width=f"{PAGE_WIDTH}", height=f"{PAGE_HEIGHT}", class_="page-guide")
    add_text(root, 28, 22, f"Page {page_index + 1}", "tiny-text", size=10)

    for slot in range(COLS * ROWS):
        card_index = page_index * COLS * ROWS + slot
        if card_index >= len(cards):
            break
        card = cards[card_index]
        row, col = divmod(slot, COLS)
        root.append(render_card(card, 0, 0, col, row, cache_dir, lilypond_bin))

    return root


def main() -> None:
    args = parse_args()
    deck = json.loads(args.input.read_text(encoding="utf-8"))
    cards = list(deck["cards"])
    pages = -(-len(cards) // (COLS * ROWS))
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for page_index in range(pages):
        root = build_page_document(deck, page_index, args.cache_dir, args.lilypond_bin)
        ET.indent(root, space="  ")
        output_path = args.output_dir / f"printable-deck-page-{page_index + 1:02d}.svg"
        ET.ElementTree(root).write(output_path, encoding="utf-8", xml_declaration=True)
        print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
