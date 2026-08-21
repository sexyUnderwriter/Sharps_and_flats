import re
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Musical note definitions
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
NOTE_MAP = {'C': 0, 'C#': 1, 'DB': 1, 'D': 2, 'D#': 3, 'EB': 3, 'E': 4,
            'F': 5, 'F#': 6, 'GB': 6, 'G': 7, 'G#': 8, 'AB': 8, 'A': 9,
            'A#': 10, 'BB': 10, 'B': 11}

def note_to_midi(note_str):
    """Converts a pitch string (e.g., 'C4') to a standard MIDI note number."""
    match = re.match(r"^([A-Ga-g][#b]?)(-?\d+)$", note_str.strip())
    if not match:
        return None
    note, octave = match.groups()
    note = note.upper()
    if note not in NOTE_MAP:
        return None
    return NOTE_MAP[note] + (int(octave) + 1) * 12

def midi_to_pitch_info(midi_num):
    """Converts MIDI number to step ('C'), alter (1 for #, 0 for natural), and octave."""
    octave = (midi_num // 12) - 1
    note_name = NOTE_NAMES[midi_num % 12]
    
    if len(note_name) > 1 and note_name[1] == '#':
        step = note_name[0]
        alter = 1
    else:
        step = note_name
        alter = 0
        
    return step, alter, octave

def string_to_alphabet_numbers(text):
    """Converts letters into their alphabetical numbers (A=1, B=2, ..., Z=26)."""
    return [(char.upper(), ord(char.upper()) - 64) for char in text if char.isalpha()]

def create_musicxml(note_data, output_filename="output.musicxml"):
    """Generates a MusicXML file containing the notes as quarter notes in 4/4 time."""
    score = ET.Element('score-partwise', version='3.1')
    
    # Part list definition
    part_list = ET.SubElement(score, 'part-list')
    score_part = ET.SubElement(part_list, 'score-part', id='P1')
    ET.SubElement(score_part, 'part-name').text = 'Melody'
    
    part = ET.SubElement(score, 'part', id='P1')
    
    # MusicXML timing setup: quarter note duration = 1 division
    DIVISIONS = 1
    quarter_notes_per_measure = 4
    
    current_measure_num = 1
    measure = ET.SubElement(part, 'measure', number=str(current_measure_num))
    
    # Measure 1 Setup Header
    attributes = ET.SubElement(measure, 'attributes')
    ET.SubElement(attributes, 'divisions').text = str(DIVISIONS)
    
    time = ET.SubElement(attributes, 'time')
    ET.SubElement(time, 'beats').text = '4'
    ET.SubElement(time, 'beat-type').text = '4'
    
    clef = ET.SubElement(attributes, 'clef')
    ET.SubElement(clef, 'sign').text = 'G'
    ET.SubElement(clef, 'line').text = '2'

    notes_in_current_measure = 0

    for letter, midi_num in note_data:
        # Create a new measure every 4 quarter notes
        if notes_in_current_measure == quarter_notes_per_measure:
            current_measure_num += 1
            measure = ET.SubElement(part, 'measure', number=str(current_measure_num))
            notes_in_current_measure = 0

        step, alter, octave = midi_to_pitch_info(midi_num)
        
        note_elem = ET.SubElement(measure, 'note')
        pitch_elem = ET.SubElement(note_elem, 'pitch')
        
        ET.SubElement(pitch_elem, 'step').text = step
        if alter != 0:
            ET.SubElement(pitch_elem, 'alter').text = str(alter)
        ET.SubElement(pitch_elem, 'octave').text = str(octave)
        
        ET.SubElement(note_elem, 'duration').text = str(DIVISIONS)
        ET.SubElement(note_elem, 'type').text = 'quarter'
        
        notes_in_current_measure += 1

    # Format into clean XML with proper header
    xml_str = ET.tostring(score, encoding='utf-8')
    parsed_xml = minidom.parseString(xml_str)
    pretty_xml = parsed_xml.toprettyxml(indent="  ")

    doctype = '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n'
    full_xml = pretty_xml.replace('<?xml version="1.0" ?>', '<?xml version="1.0" encoding="UTF-8"?>\n' + doctype)

    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(full_xml)
        
    print(f"\nSaved sheet music to '{output_filename}'")

def main():
    print("--- Text to Pitch & MusicXML Converter ---")
    user_text = input("Enter a string of letters: ")
    
    pitch_input = input("Enter a starting pitch (e.g., C4 for Middle C) [Default: C4]: ").strip()
    if not pitch_input:
        pitch_input = "C4"
        
    base_midi = note_to_midi(pitch_input)
    if base_midi is None:
        print(f"\nInvalid pitch format '{pitch_input}'. Defaulting to C4 (Middle C).")
        base_midi = 60
        pitch_input = "C4"

    letter_numbers = string_to_alphabet_numbers(user_text)
    if not letter_numbers:
        print("No valid letters found in the input string.")
        return

    note_data = []
    print("\n--- Pitch Mapping ---")
    for char, num in letter_numbers:
        semitone_offset = num - 1
        current_midi = base_midi + semitone_offset
        step, alter, octave = midi_to_pitch_info(current_midi)
        accidental = "#" if alter == 1 else ""
        
        print(f"Letter: {char} | Alphabet #: {num:2} | Note: {step}{accidental}{octave}")
        note_data.append((char, current_midi))

    # Export to MusicXML file
    create_musicxml(note_data, "output.musicxml")

if __name__ == "__main__":
    main()