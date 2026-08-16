from __future__ import annotations

import copy
import json
import random
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_DECK_PATH = Path(__file__).resolve().parents[1] / "data" / "starter-deck.json"
FAMILY_ORDER = ["C major", "F major", "G major", "D minor"]
PROGRESSION_TARGETS = [
    "G->C perfect authentic cadence",
    "F->C imperfect cadence",
    "Dm->G->C ii-V-I cadence",
]

OBJECTIVES = PROGRESSION_TARGETS
COLOR_MAP = {
    "C major": "#FF0000",
    "F major": "#FF8000",
    "G major": "#009900",
    "D minor": "#0000FF",
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


@dataclass
class PlayerState:
    player_id: str
    hand: List[str] = field(default_factory=list)
    score: int = 0
    phrase_history: List[List[str]] = field(default_factory=list)
    discards_used: int = 0


@dataclass
class GameConfig:
    player_count: int = 3
    hand_size: int = 6
    flop_size: int = 4
    discard_limit: int = 1
    rounds: int = 6
    target_family_cycle: Sequence[str] = field(default_factory=lambda: FAMILY_ORDER)
    objective_cycle: Sequence[str] = field(default_factory=lambda: OBJECTIVES)
    min_phrase_beats: int = 8
    max_phrase_beats: int = 8


@dataclass
class RoundResult:
    round_number: int
    target_family: str
    objective: str
    judge: str
    flop: List[str]
    phrases: Dict[str, List[str]]
    scores: Dict[str, float]
    winner: str
    runner_up: Optional[str]
    summary: str


@dataclass
class GameResult:
    rounds: List[RoundResult]
    final_scores: Dict[str, int]
    winner: str
    summary: str


def load_deck(deck_path: str | Path = DEFAULT_DECK_PATH) -> List[Dict[str, Any]]:
    path = Path(deck_path)
    with path.open("r", encoding="utf-8") as handle:
        deck_data = json.load(handle)
    return deck_data.get("cards", [])


def get_card_map(cards: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {card["id"]: card for card in cards}


def card_duration(card: Dict[str, Any]) -> float:
    return float(card.get("duration", 1))


def card_compatible(card: Dict[str, Any], family: str) -> bool:
    return family in card.get("familyCompatibility", []) or card.get("isRest", False)


def phrase_total_duration(cards: Sequence[Dict[str, Any]]) -> float:
    return sum(card_duration(card) for card in cards)


def validate_phrase(card_ids: Sequence[str], card_map: Dict[str, Dict[str, Any]], family: str, min_beats: int = 8, max_beats: int = 8) -> bool:
    if not card_ids:
        return False

    cards = [card_map[card_id] for card_id in card_ids]
    total_duration = phrase_total_duration(cards)
    if min_beats == max_beats:
        if total_duration != min_beats:
            return False
    elif total_duration < min_beats or total_duration > max_beats:
        return False

    for card in cards:
        if not card_compatible(card, family):
            return False
    return True


def objective_bonus(card: Dict[str, Any], objective: str) -> float:
    tags = set(card.get("tags", []))
    objective_lower = objective.lower()

    if ("g->c" in objective_lower or "perfect authentic" in objective_lower or "authentic cadence" in objective_lower):
        if any(keyword in tags for keyword in ["cadence", "leading", "dominant", "arrival", "tonic"]):
            return 2.0
        if "smooth" in tags or "supportive" in tags:
            return 1.0
        return 0.0

    if ("f->c" in objective_lower or "imperfect cadence" in objective_lower):
        if any(keyword in tags for keyword in ["subdominant", "supportive", "smooth", "tonic"]):
            return 1.8
        if "cadence" in tags or "arrival" in tags:
            return 1.0
        return 0.0

    if ("dm->g->c" in objective_lower or "ii-v-i" in objective_lower or "2-5-1" in objective_lower):
        if any(keyword in tags for keyword in ["dominant", "subdominant", "cadence", "leading", "tonic"]):
            return 2.0
        if "smooth" in tags or "supportive" in tags:
            return 1.0
        return 0.0

    if objective_lower == "tonic resolution" and "tonic" in tags:
        return 1.5
    if objective_lower == "leading-tone motion" and "leading" in tags:
        return 1.5
    if objective_lower == "smooth melodic contour" and ("smooth" in tags or "scalar" in tags):
        return 1.5
    if objective_lower == "strong rhythmic contrast" and ("triplet" in tags or "ornament" in tags):
        return 1.5
    if objective_lower == "cadential arrival" and ("cadence" in tags or "arrival" in tags):
        return 1.5
    return 0.0


def score_phrase(card_ids: Sequence[str], card_map: Dict[str, Dict[str, Any]], family: str, objective: str) -> float:
    if not card_ids:
        return float("-inf")

    cards = [card_map[card_id] for card_id in card_ids]
    if not validate_phrase(card_ids, card_map, family):
        return float("-inf")

    score = 0.0
    for card in cards:
        score += 1.5 if family in card.get("familyCompatibility", []) else 0.0
        score += objective_bonus(card, objective)
        if "tonic" in card.get("tags", []):
            score += 0.5
        if "cadence" in card.get("tags", []):
            score += 0.5
        if "leading" in card.get("tags", []):
            score += 0.4
        if "rest" in card.get("tags", []):
            score -= 0.3

    duration = phrase_total_duration(cards)
    if duration >= 6:
        score += 0.5
    if duration <= 5:
        score += 0.2
    return score


def choose_best_phrase(hand: Sequence[str], flop: Sequence[str], card_map: Dict[str, Dict[str, Any]], family: str, objective: str) -> List[str]:
    pool = list(hand) + list(flop)
    best_cards: List[str] = []
    best_score = float("-inf")

    def candidate_size_limit(size: int) -> bool:
        return size >= 1

    for size in range(1, min(len(pool), 6) + 1):
        for combo in combinations(pool, size):
            combo_list = list(combo)
            if not validate_phrase(combo_list, card_map, family):
                continue
            phrase_score = score_phrase(combo_list, card_map, family, objective)
            if phrase_score > best_score:
                best_score = phrase_score
                best_cards = combo_list

    if not best_cards:
        # Fallback: take the best single valid card from the pool.
        for card_id in pool:
            if validate_phrase([card_id], card_map, family):
                return [card_id]
        return []

    return best_cards


def choose_discard(card_ids: Sequence[str], card_map: Dict[str, Dict[str, Any]], family: str, objective: str) -> Optional[str]:
    if not card_ids:
        return None

    scored = []
    for card_id in card_ids:
        score = score_phrase([card_id], card_map, family, objective)
        scored.append((score, card_id))

    scored.sort(key=lambda item: item[0])
    if not scored:
        return None

    worst_score, worst_card = scored[0]
    if worst_score == float("-inf"):
        return worst_card
    return worst_card


def build_flop(deck: List[Dict[str, Any]], flop_size: int, rng: random.Random) -> List[Dict[str, Any]]:
    cloned = copy.deepcopy(deck)
    rng.shuffle(cloned)
    return cloned[:flop_size]


def filter_cards_for_family(cards: Sequence[Dict[str, Any]], family: str) -> List[Dict[str, Any]]:
    return [card for card in cards if family in card.get("familyCompatibility", [])]


def priority_draw_pool(cards: Sequence[Dict[str, Any]], family: str, rng: random.Random) -> List[Dict[str, Any]]:
    family_cards = filter_cards_for_family(cards, family)
    other_cards = [card for card in cards if family not in card.get("familyCompatibility", [])]
    rng.shuffle(family_cards)
    rng.shuffle(other_cards)
    return family_cards + other_cards


def deal_hands(deck: List[Dict[str, Any]], player_count: int, hand_size: int, rng: random.Random) -> Tuple[List[Dict[str, Any]], List[List[str]]]:
    cards = copy.deepcopy(deck)
    hands: List[List[str]] = [[] for _ in range(player_count)]
    for idx in range(hand_size * player_count):
        player_index = idx % player_count
        hands[player_index].append(cards.pop(0)["id"])
    return cards, hands


def resolve_round(
    players: Sequence[PlayerState],
    flop: Sequence[str],
    target_family: str,
    objective: str,
    judge: str,
    card_map: Dict[str, Dict[str, Any]],
) -> RoundResult:
    phrases: Dict[str, List[str]] = {}
    scores: Dict[str, float] = {}

    for player in players:
        if player.player_id == judge:
            continue
        phrase = choose_best_phrase(player.hand, flop, card_map, target_family, objective)
        phrases[player.player_id] = phrase
        scores[player.player_id] = score_phrase(phrase, card_map, target_family, objective)

    if not scores:
        winner = judge
        runner_up = None
        round_summary = f"Round {judge} had no eligible contestants; the judge retained the round."
    else:
        sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        winner = sorted_scores[0][0]
        runner_up = sorted_scores[1][0] if len(sorted_scores) > 1 else None

        winner_score = scores[winner]
        runner_score = scores[runner_up] if runner_up else None
        round_summary = (
            f"Target: {target_family} / {objective}. "
            f"Winner: {winner} ({winner_score:.2f}) "
            f"with {phrases[winner]}"
            f"{f' | Runner-up: {runner_up} ({runner_score:.2f})' if runner_up and runner_score is not None else ''}."
        )

    return RoundResult(
        round_number=0,
        target_family=target_family,
        objective=objective,
        judge=judge,
        flop=list(flop),
        phrases=phrases,
        scores=scores,
        winner=winner,
        runner_up=runner_up,
        summary=round_summary,
    )


def deal_initial_round(deck: List[Dict[str, Any]], config: GameConfig, rng: random.Random) -> Tuple[List[Dict[str, Any]], List[PlayerState], List[str]]:
    remaining_cards, hands = deal_hands(deck, config.player_count, config.hand_size, rng)
    flop_cards = build_flop(remaining_cards, config.flop_size, rng)
    flop_ids = [card["id"] for card in flop_cards]

    players = [
        PlayerState(player_id=f"P{i + 1}", hand=list(hand))
        for i, hand in enumerate(hands)
    ]
    return remaining_cards, players, flop_ids


def simulate_game(deck_path: str | Path = DEFAULT_DECK_PATH, config: Optional[GameConfig] = None, seed: Optional[int] = None) -> GameResult:
    if config is None:
        config = GameConfig()

    rng = random.Random(seed)
    cards = load_deck(deck_path)
    card_map = get_card_map(cards)

    players = [PlayerState(player_id=f"P{i + 1}", hand=[]) for i in range(config.player_count)]
    judge_index = 0
    rounds: List[RoundResult] = []

    for round_number in range(1, config.rounds + 1):
        judge_id = f"P{((judge_index % config.player_count) + 1)}"
        family_index = (round_number - 1) % len(config.target_family_cycle)
        objective_index = (round_number - 1) % len(config.objective_cycle)
        target_family = config.target_family_cycle[family_index]
        objective = config.objective_cycle[objective_index]

        family_cards = priority_draw_pool(cards, target_family, rng)
        if len(family_cards) < config.player_count * config.hand_size + config.flop_size:
            family_cards = copy.deepcopy(cards)
            rng.shuffle(family_cards)

        deck_for_round = copy.deepcopy(family_cards)
        remaining_cards, hands = deal_hands(deck_for_round, config.player_count, config.hand_size, rng)
        flop_cards = build_flop(remaining_cards, config.flop_size, rng)
        flop_ids = [card["id"] for card in flop_cards]

        for idx, hand in enumerate(hands):
            players[idx].hand = list(hand)
            players[idx].discards_used = 0

        for player in players:
            if player.player_id == judge_id:
                continue
            if player.discards_used >= config.discard_limit:
                continue
            discard_id = choose_discard(player.hand, card_map, target_family, objective)
            if discard_id is None:
                continue
            if discard_id in player.hand:
                player.hand.remove(discard_id)
            if remaining_cards:
                replacement = remaining_cards.pop(0)
                player.hand.append(replacement["id"])
                player.discards_used += 1

        round_result = resolve_round(players, flop_ids, target_family, objective, judge_id, card_map)
        round_result.round_number = round_number

        for player in players:
            if player.player_id == judge_id:
                continue
            if player.player_id in round_result.phrases:
                player.phrase_history.append(round_result.phrases[player.player_id])

        winner = round_result.winner
        runner_up = round_result.runner_up
        for player in players:
            if player.player_id == winner:
                player.score += 2
            elif player.player_id == runner_up:
                player.score += 1

        rounds.append(round_result)
        judge_index += 1

    final_scores = {player.player_id: player.score for player in players}
    winner_id, winner_score = max(final_scores.items(), key=lambda item: item[1])
    summary_lines = [
        f"Game complete: {winner_id} wins with {winner_score} points.",
        "Final standings:",
    ]
    for player in players:
        summary_lines.append(f"- {player.player_id}: {player.score} points")

    result = GameResult(
        rounds=rounds,
        final_scores=final_scores,
        winner=winner_id,
        summary="\n".join(summary_lines),
    )
    return result


def _add_color(el: ET.Element, family: str) -> None:
    ET.SubElement(el, "color", {"color": COLOR_MAP[family]})


def _note_to_pitch(note: Dict[str, Any]) -> ET.Element:
    pitch = ET.Element("pitch")
    ET.SubElement(pitch, "step").text = note["step"]
    ET.SubElement(pitch, "octave").text = str(note["octave"])
    alter = note.get("alter", 0)
    if alter != 0:
        ET.SubElement(pitch, "alter").text = str(alter)
    return pitch


def _card_payload(card: Dict[str, Any]) -> List[Dict[str, Any]]:
    token_type = card["tokenType"]
    notes = card.get("notes", [])

    if token_type == 0:
        return [{"kind": "rest", "duration": 960, "type": "quarter"}]
    if token_type in (1, 2, 3):
        return [{"kind": "pitch", "note": notes[0], "duration": 960, "type": "quarter"}]
    if token_type in (4, 5, 6):
        return [{"kind": "pitch", "note": note, "duration": 480, "type": "eighth"} for note in notes[:2]]
    if token_type in (7, 8):
        return [{"kind": "pitch", "note": note, "duration": 240, "type": "sixteenth"} for note in notes[:4]]
    if token_type == 9:
        return [{"kind": "pitch", "note": note, "duration": 320, "type": "eighth"} for note in notes[:3]]
    return [{"kind": "rest", "duration": 960, "type": "quarter"}]


def _render_card_measure(card: Dict[str, Any], family: str, measure_number: int) -> ET.Element:
    measure = ET.Element("measure", {"number": str(measure_number)})

    attrs = ET.SubElement(measure, "attributes")
    ET.SubElement(attrs, "divisions").text = "960"
    key = ET.SubElement(attrs, "key")
    ET.SubElement(key, "fifths").text = KEY_MAP[family]
    ET.SubElement(key, "mode").text = MODE_MAP[family]
    time = ET.SubElement(attrs, "time")
    ET.SubElement(time, "beats").text = "4"
    ET.SubElement(time, "beat-type").text = "4"
    clef = ET.SubElement(attrs, "clef")
    ET.SubElement(clef, "sign").text = "G"
    ET.SubElement(clef, "line").text = "2"

    for item in _card_payload(card):
        note_el = ET.SubElement(measure, "note")
        if item["kind"] == "rest":
            ET.SubElement(note_el, "rest")
            ET.SubElement(note_el, "duration").text = str(item["duration"])
            ET.SubElement(note_el, "type").text = item["type"]
            _add_color(note_el, family)
        else:
            note = item["note"]
            note_el.append(_note_to_pitch(note))
            ET.SubElement(note_el, "duration").text = str(item["duration"])
            ET.SubElement(note_el, "type").text = item["type"]
            alter = note.get("alter", 0)
            if alter != 0:
                ET.SubElement(note_el, "accidental").text = "sharp" if alter > 0 else "flat"
            _add_color(note_el, family)

    for _ in range(max(0, 4 - len(_card_payload(card)))):
        rest_el = ET.SubElement(measure, "note")
        ET.SubElement(rest_el, "rest")
        ET.SubElement(rest_el, "duration").text = "960"
        ET.SubElement(rest_el, "type").text = "quarter"
        _add_color(rest_el, family)

    ET.SubElement(measure, "barline", {"location": "right"})
    return measure


def render_phrase_to_musicxml(player_id: str, round_number: int, target_family: str, objective: str, phrase_ids: Sequence[str], card_map: Dict[str, Dict[str, Any]], output_path: str | Path) -> Path:
    root = ET.Element("score-partwise", {"version": "3.1"})
    work = ET.SubElement(root, "work")
    ET.SubElement(work, "work-title").text = f"Round {round_number} - {target_family} - {objective}"
    part_list = ET.SubElement(root, "part-list")
    score_part = ET.SubElement(part_list, "score-part", {"id": "P1"})
    ET.SubElement(score_part, "part-name").text = f"{player_id} phrase"
    part = ET.SubElement(root, "part", {"id": "P1"})

    if not phrase_ids:
        placeholder = ET.Element("measure", {"number": "1"})
        attrs = ET.SubElement(placeholder, "attributes")
        ET.SubElement(attrs, "divisions").text = "960"
        key = ET.SubElement(attrs, "key")
        ET.SubElement(key, "fifths").text = KEY_MAP[target_family]
        ET.SubElement(key, "mode").text = MODE_MAP[target_family]
        time = ET.SubElement(attrs, "time")
        ET.SubElement(time, "beats").text = "4"
        ET.SubElement(time, "beat-type").text = "4"
        clef = ET.SubElement(attrs, "clef")
        ET.SubElement(clef, "sign").text = "G"
        ET.SubElement(clef, "line").text = "2"
        rest = ET.SubElement(placeholder, "note")
        ET.SubElement(rest, "rest")
        ET.SubElement(rest, "duration").text = "960"
        ET.SubElement(rest, "type").text = "whole"
        _add_color(rest, target_family)
        ET.SubElement(placeholder, "barline", {"location": "right"})
        part.append(placeholder)
    else:
        for index, card_id in enumerate(phrase_ids, start=1):
            card = card_map[card_id]
            part.append(_render_card_measure(card, target_family, index))

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)
    return output


def export_round_musicxml(round_result: RoundResult, card_map: Dict[str, Dict[str, Any]], export_dir: str | Path) -> List[Path]:
    export_root = Path(export_dir)
    export_root.mkdir(parents=True, exist_ok=True)
    exported: List[Path] = []

    # Create one combined file with a separate staff per player.
    combined_path = export_root / f"round_{round_result.round_number:02d}_all_players_{round_result.target_family.replace(' ', '_')}.musicxml"

    root = ET.Element("score-partwise", {"version": "3.1"})
    work = ET.SubElement(root, "work")
    ET.SubElement(work, "work-title").text = f"Round {round_result.round_number} - {round_result.target_family} - {round_result.objective}"
    part_list = ET.SubElement(root, "part-list")

    all_player_ids = list(round_result.phrases.keys())
    if round_result.judge not in all_player_ids:
        all_player_ids.append(round_result.judge)

    for player_id in all_player_ids:
        phrase = round_result.phrases.get(player_id, [])
        score_part = ET.SubElement(part_list, "score-part", {"id": player_id})
        ET.SubElement(score_part, "part-name").text = player_id
        part = ET.SubElement(root, "part", {"id": player_id})

        if not phrase:
            placeholder = ET.Element("measure", {"number": "1"})
            attrs = ET.SubElement(placeholder, "attributes")
            ET.SubElement(attrs, "divisions").text = "960"
            key = ET.SubElement(attrs, "key")
            ET.SubElement(key, "fifths").text = KEY_MAP[round_result.target_family]
            ET.SubElement(key, "mode").text = MODE_MAP[round_result.target_family]
            time = ET.SubElement(attrs, "time")
            ET.SubElement(time, "beats").text = "4"
            ET.SubElement(time, "beat-type").text = "4"
            clef = ET.SubElement(attrs, "clef")
            ET.SubElement(clef, "sign").text = "G"
            ET.SubElement(clef, "line").text = "2"
            rest = ET.SubElement(placeholder, "note")
            ET.SubElement(rest, "rest")
            ET.SubElement(rest, "duration").text = "960"
            ET.SubElement(rest, "type").text = "whole"
            _add_color(rest, round_result.target_family)
            ET.SubElement(placeholder, "barline", {"location": "right"})
            part.append(placeholder)
        else:
            for index, card_id in enumerate(phrase, start=1):
                card = card_map[card_id]
                part.append(_render_card_measure(card, round_result.target_family, index))

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(combined_path, encoding="utf-8", xml_declaration=True)
    exported.append(combined_path)

    for player_id, phrase in round_result.phrases.items():
        filename = f"round_{round_result.round_number:02d}_{player_id}_{round_result.target_family.replace(' ', '_')}.musicxml"
        path = export_root / filename
        render_phrase_to_musicxml(
            player_id=player_id,
            round_number=round_result.round_number,
            target_family=round_result.target_family,
            objective=round_result.objective,
            phrase_ids=phrase,
            card_map=card_map,
            output_path=path,
        )
        exported.append(path)
    return exported


def simulate_game(
    deck_path: str | Path = DEFAULT_DECK_PATH,
    config: Optional[GameConfig] = None,
    seed: Optional[int] = None,
    export_musicxml_dir: Optional[str | Path] = None,
) -> GameResult:
    if config is None:
        config = GameConfig()

    rng = random.Random(seed)
    cards = load_deck(deck_path)
    card_map = get_card_map(cards)

    players = [PlayerState(player_id=f"P{i + 1}", hand=[]) for i in range(config.player_count)]
    judge_index = 0
    rounds: List[RoundResult] = []

    for round_number in range(1, config.rounds + 1):
        judge_id = f"P{((judge_index % config.player_count) + 1)}"
        family_index = (round_number - 1) % len(config.target_family_cycle)
        objective_index = (round_number - 1) % len(config.objective_cycle)
        target_family = config.target_family_cycle[family_index]
        objective = config.objective_cycle[objective_index]

        family_cards = priority_draw_pool(cards, target_family, rng)
        if len(family_cards) < config.player_count * config.hand_size + config.flop_size:
            family_cards = copy.deepcopy(cards)
            rng.shuffle(family_cards)

        deck_for_round = copy.deepcopy(family_cards)
        remaining_cards, hands = deal_hands(deck_for_round, config.player_count, config.hand_size, rng)
        flop_cards = build_flop(remaining_cards, config.flop_size, rng)
        flop_ids = [card["id"] for card in flop_cards]

        for idx, hand in enumerate(hands):
            players[idx].hand = list(hand)

        round_result = resolve_round(players, flop_ids, target_family, objective, judge_id, card_map)
        round_result.round_number = round_number

        for player in players:
            if player.player_id == judge_id:
                continue
            if player.player_id in round_result.phrases:
                player.phrase_history.append(round_result.phrases[player.player_id])

        winner = round_result.winner
        runner_up = round_result.runner_up
        for player in players:
            if player.player_id == winner:
                player.score += 2
            elif player.player_id == runner_up:
                player.score += 1

        rounds.append(round_result)
        judge_index += 1

        if export_musicxml_dir is not None:
            export_round_musicxml(round_result, card_map, Path(export_musicxml_dir) / f"round_{round_number:02d}")

    final_scores = {player.player_id: player.score for player in players}
    winner_id, winner_score = max(final_scores.items(), key=lambda item: item[1])
    summary_lines = [
        f"Game complete: {winner_id} wins with {winner_score} points.",
        "Final standings:",
    ]
    for player in players:
        summary_lines.append(f"- {player.player_id}: {player.score} points")

    result = GameResult(
        rounds=rounds,
        final_scores=final_scores,
        winner=winner_id,
        summary="\n".join(summary_lines),
    )
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Simulate a prototype tonal phrase card game and optionally export MusicXML phrases for each round.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--players", type=int, default=3)
    parser.add_argument("--hand-size", type=int, default=5)
    parser.add_argument("--flop-size", type=int, default=4)
    parser.add_argument("--export-musicxml", type=str, default=None, help="Directory to write MusicXML phrase exports for each round and player.")
    args = parser.parse_args()

    config = GameConfig(
        player_count=args.players,
        hand_size=args.hand_size,
        flop_size=args.flop_size,
        rounds=args.rounds,
    )
    game_result = simulate_game(config=config, seed=args.seed, export_musicxml_dir=args.export_musicxml)
    print(game_result.summary)
    print()
    for round_result in game_result.rounds:
        print(f"Round {round_result.round_number}: {round_result.summary}")


if __name__ == "__main__":
    main()
