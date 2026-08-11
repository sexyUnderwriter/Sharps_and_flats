#!/usr/bin/env python3
"""Convert any single-part, two-staff MusicXML file straight to a Humdrum
**kern file, using the same parsing/encoding approach as
tools/tokenize_bars.py + tools/bars_to_humdrum.py (no chord labeling or
bars.json intermediate needed, since this is for stand-alone scores).

Usage: python3 tools/xml_to_kern.py [input.xml] [output.krn]
Defaults to converting "Descending motifs.xml" -> "data/Descending motifs.krn".
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TYPE_TO_VEX = {
    "whole": "w",
    "half": "h",
    "quarter": "q",
    "eighth": "8",
    "16th": "16",
    "32nd": "32",
    "64th": "64",
    "128th": "128",
}

VEX_BASE_TO_KERN = {"w": 1, "h": 2, "q": 4, "8": 8, "16": 16, "32": 32, "64": 64, "128": 128}

# Fallback (base_code, dots) for events lacking a notated <type> (e.g. a
# blank measure), keyed by exact tick count at divisions=12 (quarter=12 ticks).
FALLBACK_TICKS = {
    48: ("w", 0),
    36: ("h", 1),
    24: ("h", 0),
    18: ("q", 1),
    12: ("q", 0),
    9: ("8", 1),
    6: ("8", 0),
    3: ("16", 0),
}


def vex_duration_for(type_text, dots, is_rest, duration, divisions):
    base = TYPE_TO_VEX.get(type_text)
    if base is None:
        scale = divisions / 12
        base, dots = FALLBACK_TICKS.get(round(duration / scale), ("q", 0))
    code = base + ("d" * dots)
    if is_rest:
        code += "r"
    return code


def parse_measure(measure_el, divisions):
    """Return {'1': [raw events], '2': [raw events]} keyed by staff number."""
    voices = {"1": [], "2": []}
    last_staff = None
    for child in measure_el:
        tag = child.tag
        if tag == "note":
            staff = child.findtext("staff") or last_staff or "1"
            last_staff = staff
            duration = int(child.findtext("duration", "0"))
            is_rest = child.find("rest") is not None
            tie_start = any(t.get("type") == "start" for t in child.findall("tie"))
            tie_stop = any(t.get("type") == "stop" for t in child.findall("tie"))
            type_text = child.findtext("type")
            dots = len(child.findall("dot"))
            vex_duration = vex_duration_for(type_text, dots, is_rest, duration, divisions)

            tuplet_start = tuplet_stop = False
            tuplet_actual = tuplet_normal = None
            notations_el = child.find("notations")
            if notations_el is not None:
                for tup in notations_el.findall("tuplet"):
                    if tup.get("type") == "start":
                        tuplet_start = True
                    elif tup.get("type") == "stop":
                        tuplet_stop = True
            if tuplet_start:
                tm = child.find("time-modification")
                if tm is not None:
                    tuplet_actual = int(tm.findtext("actual-notes"))
                    tuplet_normal = int(tm.findtext("normal-notes"))

            entry = {
                "type": "rest" if is_rest else "note",
                "duration": duration,
                "vexDuration": vex_duration,
                "tieStart": tie_start,
                "tieStop": tie_stop,
                "tupletStart": tuplet_start,
                "tupletStop": tuplet_stop,
            }
            if tuplet_actual is not None:
                entry["tupletActual"] = tuplet_actual
                entry["tupletNormal"] = tuplet_normal
            if not is_rest:
                pitch = child.find("pitch")
                entry["step"] = pitch.findtext("step")
                entry["alter"] = int(pitch.findtext("alter", "0"))
                entry["octave"] = int(pitch.findtext("octave"))
            voices.setdefault(staff, []).append(entry)
        elif tag == "forward":
            duration = int(child.findtext("duration", "0"))
            staff = last_staff or "1"
            vex_duration = vex_duration_for(None, 0, True, duration, divisions)
            voices.setdefault(staff, []).append(
                {
                    "type": "rest",
                    "duration": duration,
                    "vexDuration": vex_duration,
                    "tieStart": False,
                    "tieStop": False,
                    "tupletStart": False,
                    "tupletStop": False,
                }
            )
        elif tag == "backup":
            pass  # only rewinds the authoring cursor; events are grouped by staff already
    return voices


def kern_pitch(step, alter, octave):
    if octave >= 4:
        letter = step.lower()
        reps = octave - 3
    else:
        letter = step.upper()
        reps = 4 - octave
    accidental = "#" * alter if alter > 0 else "-" * (-alter)
    return letter * reps + accidental


def kern_duration(vex_duration, tuplet_actual, tuplet_normal):
    code = vex_duration
    is_rest = code.endswith("r")
    if is_rest:
        code = code[:-1]
    dots = 0
    while code.endswith("d"):
        dots += 1
        code = code[:-1]
    base = VEX_BASE_TO_KERN[code]
    if tuplet_actual and tuplet_normal:
        base = base * tuplet_actual // tuplet_normal
    return f"{base}{'.' * dots}", is_rest


def kern_token(event, tuplet_actual, tuplet_normal):
    dur, is_rest = kern_duration(event["vexDuration"], tuplet_actual, tuplet_normal)
    if is_rest:
        return f"{dur}r"
    pitch = kern_pitch(event["step"], event.get("alter", 0), event["octave"])
    tie_start, tie_stop = event.get("tieStart"), event.get("tieStop")
    tie = "_" if tie_start and tie_stop else "[" if tie_start else "]" if tie_stop else ""
    return f"{dur}{pitch}{tie}"


def onsets_with_tokens(events):
    result = []
    t = 0
    tuplet_actual = tuplet_normal = None
    for ev in events:
        if ev.get("tupletStart"):
            tuplet_actual = ev.get("tupletActual")
            tuplet_normal = ev.get("tupletNormal")
        result.append((t, kern_token(ev, tuplet_actual, tuplet_normal)))
        if ev.get("tupletStop"):
            tuplet_actual = tuplet_normal = None
        t += ev["duration"]
    return result


def main():
    xml_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "Descending motifs.xml"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / (xml_path.stem + ".krn")

    tree = ET.parse(xml_path)
    root = tree.getroot()
    part = root.find("part")

    divisions = 12
    tempo = 120
    beats, beat_type = 4, 4

    lines = [
        f"!!!OTL: {root.findtext('movement-title', xml_path.stem)}",
        "**kern\t**kern",
        "*staff1\t*staff2",
        "*Ipiano\t*Ipiano",
        "*clefG2\t*clefF4",
    ]
    tempo_written = time_written = False
    written = 0

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

        sound_el = measure_el.find(".//sound[@tempo]")
        if sound_el is not None:
            tempo = float(sound_el.get("tempo"))

        if not time_written:
            lines.append(f"*M{beats}/{beat_type}\t*M{beats}/{beat_type}")
            time_written = True
        if not tempo_written and sound_el is not None:
            lines.append(f"*MM{round(tempo)}\t*MM{round(tempo)}")
            tempo_written = True

        ticks_per_bar = divisions * beats * 4 // beat_type
        raw_voices = parse_measure(measure_el, divisions)

        for staff_key in ("1", "2"):
            events = raw_voices.get(staff_key) or []
            if sum(e["duration"] for e in events) == 0:
                raw_voices[staff_key] = [
                    {
                        "type": "rest",
                        "duration": ticks_per_bar,
                        "vexDuration": vex_duration_for(None, 0, True, ticks_per_bar, divisions),
                        "tieStart": False,
                        "tieStop": False,
                        "tupletStart": False,
                        "tupletStop": False,
                    }
                ]

        # Skip measures that are silent in both staves (nothing but rests) -
        # a redundant whole-bar rest carries no information for analysis.
        if all(e["type"] == "rest" for e in raw_voices["1"]) and all(
            e["type"] == "rest" for e in raw_voices["2"]
        ):
            continue

        written += 1
        lines.append("=\t=")
        treble = dict(onsets_with_tokens(raw_voices["1"]))
        bass = dict(onsets_with_tokens(raw_voices["2"]))
        for onset in sorted(set(treble) | set(bass)):
            lines.append(f"{treble.get(onset, '.')}\t{bass.get(onset, '.')}")

    lines.append("==\t==")
    lines.append("*-\t*-")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    total = len(part.findall("measure"))
    print(f"Wrote {written} measures of Humdrum **kern data to {out_path} ({total - written} silent measures omitted)")


if __name__ == "__main__":
    main()
