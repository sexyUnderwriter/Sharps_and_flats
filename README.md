# Sharps and Flats

Prototype tonal phrase card game built from beat-sized musical tokens.

## What this branch contains

- 120-card starter deck
- MusicXML exports for the deck and simulation rounds
- A phrase simulator for 2–4 players
- Progression-based round targets:
  - G → C
  - F → C
  - Dm → G → C
- A balance harness for raw vs progression-weighted dealing

## Core ideas

- Each card is one beat.
- Phrases are exactly 8 beats.
- Players use a 6-card hand plus a shared flop.
- Cards can be compatible with multiple tonal families.
- Round scoring is based on musical fit, not strict theory correctness.

## Repository layout

- `game_engine/simulator.py` — main game logic, scoring, dealing, and MusicXML export
- `simulate_game.py` — CLI runner for one simulation
- `balance_simulation.py` — balance matrix runner
- `tools/generate_deck_musicxml.py` — deck-to-MusicXML export
- `tools/generate_printable_deck_lilypond.py` — LilyPond-backed printable SVG sheet export
- `tools/update_deck_compatibility.py` — recomputes multi-family legality and fit
- `data/starter-deck.json` — current 120-card deck source of truth
- `data/starter-deck.musicxml` — deck notation export
- `data/round_exports/` — simulation round exports
- `deck.schema.json` — deck schema
- `game prompt v2` — current design notes
- `deck specification document` — deck and token design notes

## Getting started

Create or activate the project environment, then run:

```bash
python simulate_game.py
```

## Useful commands

Generate the deck score:

```bash
python tools/generate_deck_musicxml.py
```

Generate printable SVG pages with LilyPond-rendered notation:

```bash
python tools/generate_printable_deck_lilypond.py
```

Run a simulation and export round MusicXML:

```bash
cd /Users/chrisarehart/Sharps_and_flats && python simulate_game.py --rounds 6 --seed 42 --export-musicxml data/round_exports
```

Recompute deck compatibility metadata:

```bash
python tools/update_deck_compatibility.py
```

Run the balance matrix:

```bash
python balance_simulation.py --games 10000 --scored-games 25 --mode both --workers 8 --output data/balance-report.json
```

## Current simulation model

- **Balanced mode**: progression-weighted deals that guarantee playable phrases for the current targets.
- **Raw mode**: shuffled deck dealing with the same scoring and compatibility rules.
- **Progression zones**:
  - G → C: 4 G-family beats, then 4 C-family beats
  - F → C: 4 F-family beats, then 4 C-family beats
  - Dm → G → C: 2 D-family beats, 2 G-family beats, then 4 C-family beats

## Generated artifacts

- `data/starter-deck.musicxml`
- `data/round_exports/*`
- `data/balance-report.json`
- `data/lilypond-cache/*`
- `data/printable-deck-pages/*.svg`

## Notes

- Cards now carry `primaryFamily`, multi-family `familyCompatibility`, and per-family fit scores.
- The simulator can arrange hand and flop cards in any order, as long as each beat lands in a legal progression zone.
- MusicXML exports label each token with hand/flop provenance and assigned progression family.
- Printable sheet rendering requires LilyPond on PATH.
