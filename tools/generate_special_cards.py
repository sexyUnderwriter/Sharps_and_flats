#!/usr/bin/env python3
"""Generate a printable PDF sheet of optional phrase-deck special cards."""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path
import xml.etree.ElementTree as ET

PAGE_WIDTH = 816
PAGE_HEIGHT = 1056
CARD_WIDTH = 224
CARD_HEIGHT = 314
POSITIONS = ((52, 42), (296, 42), (540, 42), (174, 392), (418, 392))
METER_GLYPH_VIEW_BOX = "0.7 0.7 2.2 4.6"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def element(tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    if "class_" in attrs:
        attrs["class"] = attrs.pop("class_")
    node = ET.Element(f"{{{NS}}}{tag}", attrs)
    if text is not None:
        node.text = text
    return node


def add(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    node = element(tag, text, **attrs)
    parent.append(node)
    return node


def add_text(parent: ET.Element, x: float, y: float, text: str, css_class: str, size: int, anchor: str = "start") -> None:
    add(parent, "text", text, x=str(x), y=str(y), class_=css_class, **{"font-size": str(size), "text-anchor": anchor})


def wrapped_lines(text: str, width: int = 31) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if line and len(candidate) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def render_meter_svg(card: dict[str, object], cache_dir: Path) -> ET.Element:
        cache_dir.mkdir(parents=True, exist_ok=True)
        stem = str(card["id"]).lower()
        lilypond_source = textwrap.dedent(
                f"""\
                \\version "2.24.0"
                #(set-global-staff-size 64)
                \\paper {{
                    #(set-paper-size "a6")
                    top-margin = 0
                    bottom-margin = 0
                    left-margin = 0
                    right-margin = 0
                    indent = 0
                    tagline = ##f
                    print-page-number = ##f
                }}
                \\score {{
                    \\new Staff \\with {{
                        \\remove "Clef_engraver"
                        \\remove "Staff_symbol_engraver"
                        \\remove "Bar_engraver"
                    }} {{
                        \\numericTimeSignature
                        \\time {card['beatsPerBar']}/4
                        s1
                    }}
                }}
                """
        )
        ly_path = cache_dir / f"{stem}.ly"
        svg_path = cache_dir / f"{stem}.svg"
        ly_path.write_text(lilypond_source, encoding="utf-8")
        if not svg_path.exists() or svg_path.stat().st_mtime < ly_path.stat().st_mtime:
                subprocess.run(
                        ["lilypond", "-dbackend=svg", "-dno-point-and-click", "-o", stem, ly_path.name],
                        cwd=cache_dir,
                        check=True,
                        capture_output=True,
                        text=True,
                )
        source_root = ET.parse(svg_path).getroot()
        embedded = element(
                "svg",
                    x="16",
                    y="16",
                    width=str(CARD_WIDTH - 32),
                    height=str(CARD_HEIGHT - 32),
                preserveAspectRatio="xMidYMid meet",
                        viewBox=METER_GLYPH_VIEW_BOX,
        )
        for child in list(source_root):
                embedded.append(child)
        return embedded


def render_icon(group: ET.Element, card: dict[str, object]) -> None:
    kind = card["kind"]
    if kind == "phrase-effect" and card["id"] == "SP-REPEAT":
        add_text(group, CARD_WIDTH / 2, 125, "||:  :||", "notation", 42, "middle")
    elif kind == "phrase-effect":
        add(group, "line", x1="54", y1="124", x2="168", y2="124", class_="staff")
        add(group, "ellipse", cx="65", cy="124", rx="8", ry="6", class_="note")
        add(group, "ellipse", cx="157", cy="124", rx="8", ry="6", class_="note")
        add(group, "path", d="M 72 118 Q 111 88 150 118", class_="tie")
 

def render_card(root: ET.Element, card: dict[str, object], x: int, y: int, cache_dir: Path) -> None:
    group = add(root, "g", transform=f"translate({x},{y})")
    is_meter = card["kind"] == "meter"
    color = "#326fa8" if is_meter else "#c65b28"
    add(group, "rect", x="0", y="0", width=str(CARD_WIDTH), height=str(CARD_HEIGHT), rx="10", ry="10", class_="card")
    if is_meter:
        group.append(render_meter_svg(card, cache_dir))
        return
    add(group, "rect", x="0", y="0", width=str(CARD_WIDTH), height="46", rx="10", ry="10", fill=color)
    add_text(group, CARD_WIDTH / 2, 30, str(card["name"]).upper(), "title", 16, "middle")
    render_icon(group, card)
    add(group, "line", x1="18", y1="184", x2=str(CARD_WIDTH - 18), y2="184", class_="divider")
    for index, line in enumerate(wrapped_lines(str(card["rule"]))):
        add_text(group, CARD_WIDTH / 2, 210 + index * 15, line, "rule", 10, "middle")


def main() -> None:
    root_dir = Path(__file__).resolve().parents[1]
    cache_dir = root_dir / "data/special-card-cache"
    data = json.loads((root_dir / "data/special-cards.json").read_text(encoding="utf-8"))
    root = element("svg", width="8.5in", height="11in", viewBox=f"0 0 {PAGE_WIDTH} {PAGE_HEIGHT}", version="1.1")
    style = add(root, "style")
    style.text = """
      .page { fill: #f4f0e7; }
      .card { fill: #fffdf9; stroke: #202b33; stroke-width: 1.3; }
      .title { fill: #fff; font-family: Georgia, serif; font-weight: 700; letter-spacing: 0; }
      .notation, .meter { fill: #202b33; font-family: Georgia, serif; font-weight: 700; }
      .staff, .tie { fill: none; stroke: #202b33; stroke-width: 2.3; stroke-linecap: round; }
      .note { fill: #202b33; }
      .divider { stroke: #d5d0c5; stroke-width: 1; }
      .rule { fill: #36424b; font-family: Helvetica, sans-serif; }
    """
    add(root, "rect", x="0", y="0", width=str(PAGE_WIDTH), height=str(PAGE_HEIGHT), class_="page")
    for card, (x, y) in zip(data["cards"], POSITIONS):
        render_card(root, card, x, y, cache_dir)
    output = root_dir / "data/special-cards.pdf"
    svg_output = root_dir / "data/special-cards.svg"
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(svg_output, encoding="utf-8", xml_declaration=True)
    inkscape = shutil.which("inkscape") or "/Applications/Inkscape.app/Contents/MacOS/inkscape"
    subprocess.run([inkscape, "--export-type=pdf", f"--export-filename={output}", str(svg_output)], check=True)
    print(f"Wrote {svg_output}\nWrote {output}")


if __name__ == "__main__":
    main()