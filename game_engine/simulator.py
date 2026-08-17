from __future__ import annotations

import copy
import json
import random
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from math import comb, isfinite
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_DECK_PATH = Path(__file__).resolve().parents[1] / "data" / "starter-deck.json"
FAMILY_ORDER = ["C major", "F major", "G major", "D minor"]
PROGRESSION_TARGETS = [
    "G->C perfect authentic cadence",
    "F->C imperfect cadence",
    "Dm->G->C ii-V-I cadence",
]
PROGRESSION_ZONES = {
    PROGRESSION_TARGETS[0]: (("G major", 4), ("C major", 4)),
    PROGRESSION_TARGETS[1]: (("F major", 4), ("C major", 4)),
    PROGRESSION_TARGETS[2]: (("D minor", 2), ("G major", 2), ("C major", 4)),
}

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
    deal_mode: str = "raw"
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
    hands: Dict[str, List[str]]
    discards_used: Dict[str, int]
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
    return family in card.get("familyCompatibility", [])


def phrase_total_duration(cards: Sequence[Dict[str, Any]]) -> float:
    return sum(card_duration(card) for card in cards)


def progression_families(objective: str, fallback_family: str = "C major") -> List[str]:
    for progression, zones in PROGRESSION_ZONES.items():
        if progression == objective:
            return [family for family, beats in zones for _ in range(beats)]
    return [fallback_family] * 8


def progression_resolution_family(objective: str, fallback_family: str = "C major") -> str:
    return progression_families(objective, fallback_family)[-1]


def count_legal_phrase_selections(
    hand: Sequence[str],
    flop: Sequence[str],
    card_map: Dict[str, Dict[str, Any]],
    objective: str,
    fallback_family: str = "C major",
) -> int:
    required_counts = Counter(progression_families(objective, fallback_family))
    required_families = tuple(required_counts)
    category_counts = [0] * (1 << len(required_families))
    for card_id in list(hand) + list(flop):
        compatibility = set(card_map[card_id].get("familyCompatibility", []))
        category_mask = sum(
            1 << index
            for index, family in enumerate(required_families)
            if family in compatibility
        )
        if category_mask:
            category_counts[category_mask] += 1
    return _count_assignable_subsets(
        tuple(category_counts),
        tuple(required_counts[family] for family in required_families),
    )


@lru_cache(maxsize=8192)
def _count_assignable_subsets(
    category_counts: Tuple[int, ...],
    requirements: Tuple[int, ...],
) -> int:
    family_count = len(requirements)
    target_cards = sum(requirements)
    categories = [
        (mask, count)
        for mask, count in enumerate(category_counts)
        if mask and count
    ]
    selected_counts = [0] * len(categories)

    def selection_is_assignable() -> bool:
        states = {(0,) * family_count}
        for category_index, (mask, _) in enumerate(categories):
            for _ in range(selected_counts[category_index]):
                next_states = set()
                for state in states:
                    for family_index in range(family_count):
                        if mask & (1 << family_index) and state[family_index] < requirements[family_index]:
                            updated = list(state)
                            updated[family_index] += 1
                            next_states.add(tuple(updated))
                states = next_states
                if not states:
                    return False
        return requirements in states

    def count_selections(category_index: int, selected_total: int, ways: int) -> int:
        if category_index == len(categories):
            return ways if selected_total == target_cards and selection_is_assignable() else 0

        _, available = categories[category_index]
        remaining_slots = target_cards - selected_total
        total = 0
        for selected in range(min(available, remaining_slots) + 1):
            selected_counts[category_index] = selected
            total += count_selections(
                category_index + 1,
                selected_total + selected,
                ways * comb(available, selected),
            )
        selected_counts[category_index] = 0
        return total

    return count_selections(0, 0, 1)


def _card_fits_progression_position(
    card: Dict[str, Any],
    beat_position: float,
    objective: str,
    fallback_family: str,
) -> bool:
    required_families = progression_families(objective, fallback_family)
    duration = card_duration(card)
    start_beat = int(beat_position)
    end_beat = int(beat_position + duration)
    if beat_position != start_beat or duration != end_beat - start_beat:
        return False
    if end_beat > len(required_families):
        return False
    return all(card_compatible(card, required_families[beat]) for beat in range(start_beat, end_beat))


def validate_phrase(
    card_ids: Sequence[str],
    card_map: Dict[str, Dict[str, Any]],
    family: str,
    min_beats: int = 8,
    max_beats: int = 8,
    objective: Optional[str] = None,
) -> bool:
    if not card_ids:
        return False

    cards = [card_map[card_id] for card_id in card_ids]
    total_duration = phrase_total_duration(cards)
    if min_beats == max_beats:
        if total_duration != min_beats:
            return False
    elif total_duration < min_beats or total_duration > max_beats:
        return False

    elapsed_beats = 0.0
    for card in cards:
        if objective is None:
            compatible = card_compatible(card, family)
        else:
            compatible = _card_fits_progression_position(card, elapsed_beats, objective, family)
        if not compatible:
            return False
        elapsed_beats += card_duration(card)
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


def _card_score(card: Dict[str, Any], family: str, objective: str) -> float:
    family_fit = float(card.get("familyFit", {}).get(family, 0.0))
    primary_weight = 1.0 if card.get("primaryFamily") == family else 0.35
    score = 0.0
    score += 1.5 * family_fit
    score += objective_bonus(card, objective) * primary_weight
    if "tonic" in card.get("tags", []):
        score += 0.5 * primary_weight
    if "cadence" in card.get("tags", []):
        score += 0.5 * primary_weight
    if "leading" in card.get("tags", []):
        score += 0.4 * primary_weight
    if "rest" in card.get("tags", []):
        score -= 0.3
    return score


def _pitch_number(note: Dict[str, Any]) -> int:
    pitch_classes = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    return (int(note["octave"]) + 1) * 12 + pitch_classes[note["step"]] + int(note.get("alter", 0))


def _transition_bonus(previous_card: Dict[str, Any], next_card: Dict[str, Any]) -> float:
    if previous_card.get("isRest", False) or next_card.get("isRest", False):
        return 0.0
    previous_notes = previous_card.get("notes", [])
    next_notes = next_card.get("notes", [])
    if not previous_notes or not next_notes:
        return 0.0

    interval = abs(_pitch_number(previous_notes[-1]) - _pitch_number(next_notes[0]))
    if interval <= 2:
        return 1.0
    if interval <= 5:
        return 0.4
    if interval <= 7:
        return 0.0
    return -0.6


def _position_bonus(card: Dict[str, Any], objective: str, beat_position: float) -> float:
    tags = set(card.get("tags", []))
    objective_lower = objective.lower()
    score = 0.0

    if beat_position >= 7:
        if tags & {"tonic", "arrival", "cadence"}:
            score += 2.5
        if "rest" in tags:
            score -= 1.0

    if "dm->g->c" in objective_lower or "ii-v-i" in objective_lower or "2-5-1" in objective_lower:
        if beat_position < 3 and "subdominant" in tags:
            score += 1.0
        if 3 <= beat_position < 6 and tags & {"dominant", "leading"}:
            score += 1.0
        if beat_position >= 6 and tags & {"tonic", "arrival", "cadence"}:
            score += 1.2
    elif "f->c" in objective_lower or "imperfect cadence" in objective_lower:
        if beat_position < 5 and "subdominant" in tags:
            score += 0.9
        if beat_position >= 6 and tags & {"tonic", "arrival", "cadence"}:
            score += 1.2
    elif "g->c" in objective_lower or "perfect authentic" in objective_lower or "authentic cadence" in objective_lower:
        if 4 <= beat_position < 7 and tags & {"dominant", "leading"}:
            score += 1.0
        if beat_position >= 7 and tags & {"tonic", "arrival", "cadence"}:
            score += 1.5
    return score


def score_phrase(card_ids: Sequence[str], card_map: Dict[str, Dict[str, Any]], family: str, objective: str) -> float:
    if not card_ids or not validate_phrase(card_ids, card_map, family, objective=objective):
        return float("-inf")

    cards = [card_map[card_id] for card_id in card_ids]
    required_families = progression_families(objective, family)
    score = 0.0
    elapsed_beats = 0.0
    for index, card in enumerate(cards):
        required_family = required_families[int(elapsed_beats)]
        score += _card_score(card, required_family, objective)
        score += _position_bonus(card, objective, elapsed_beats)
        if index:
            score += _transition_bonus(cards[index - 1], card)
        elapsed_beats += card_duration(card)
    score += 0.5
    return score


def choose_best_phrase(hand: Sequence[str], flop: Sequence[str], card_map: Dict[str, Dict[str, Any]], family: str, objective: str) -> List[str]:
    pool = list(hand) + list(flop)
    if count_legal_phrase_selections(hand, flop, card_map, objective, family) == 0:
        return []
    cards = [card_map[card_id] for card_id in pool]
    target_beats = 8.0
    states: Dict[int, Dict[int, Tuple[float, List[int], float]]] = {}
    best_score = float("-inf")
    best_sequence: List[int] = []
    required_families = progression_families(objective, family)

    for index, card in enumerate(cards):
        duration = card_duration(card)
        if not _card_fits_progression_position(card, 0.0, objective, family) or duration > target_beats:
            continue
        initial_score = _card_score(card, required_families[0], objective) + _position_bonus(card, objective, 0.0)
        states.setdefault(1 << index, {})[index] = (initial_score, [index], duration)

    for mask in range(1, 1 << len(cards)):
        for last_index, (state_score, sequence, elapsed_beats) in states.get(mask, {}).items():
            if elapsed_beats == target_beats:
                final_score = state_score + 0.5
                if final_score > best_score:
                    best_score = final_score
                    best_sequence = sequence
                continue

            for next_index, next_card in enumerate(cards):
                if mask & (1 << next_index):
                    continue
                next_duration = card_duration(next_card)
                new_elapsed_beats = elapsed_beats + next_duration
                if new_elapsed_beats > target_beats:
                    continue
                if not _card_fits_progression_position(next_card, elapsed_beats, objective, family):
                    continue
                required_family = required_families[int(elapsed_beats)]
                new_score = (
                    state_score
                    + _card_score(next_card, required_family, objective)
                    + _position_bonus(next_card, objective, elapsed_beats)
                    + _transition_bonus(cards[last_index], next_card)
                )
                new_mask = mask | (1 << next_index)
                new_mask_states = states.setdefault(new_mask, {})
                existing_state = new_mask_states.get(next_index)
                if existing_state is None or new_score > existing_state[0]:
                    new_mask_states[next_index] = (new_score, sequence + [next_index], new_elapsed_beats)

    return [pool[index] for index in best_sequence]


def choose_discard(
    card_ids: Sequence[str],
    card_map: Dict[str, Dict[str, Any]],
    family: str,
    objective: str,
    flop: Sequence[str] = (),
) -> Optional[str]:
    if not card_ids:
        return None

    current_choices = count_legal_phrase_selections(card_ids, flop, card_map, objective, family)
    required_families = set(progression_families(objective, family))
    scored = []
    for card_index, card_id in enumerate(card_ids):
        card = card_map[card_id]
        trial_hand = list(card_ids)
        trial_hand.pop(card_index)
        remaining_choices = count_legal_phrase_selections(trial_hand, flop, card_map, objective, family)
        if current_choices and not remaining_choices:
            continue
        best_fit = max(
            (float(card.get("familyFit", {}).get(required_family, 0.0)) for required_family in required_families),
            default=0.0,
        )
        score = best_fit - 0.05 * remaining_choices
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


def deal_hands(deck: List[Dict[str, Any]], player_count: int, hand_size: int) -> Tuple[List[Dict[str, Any]], List[List[str]]]:
    cards = copy.deepcopy(deck)
    hands: List[List[str]] = [[] for _ in range(player_count)]
    for idx in range(hand_size * player_count):
        player_index = idx % player_count
        hands[player_index].append(cards.pop(0)["id"])
    return cards, hands


def build_progression_ready_round(
    deck: Sequence[Dict[str, Any]],
    objective: str,
    player_count: int,
    hand_size: int,
    flop_size: int,
    rng: random.Random,
) -> Tuple[List[Dict[str, Any]], List[List[str]], List[str]]:
    required_families = progression_families(objective)
    required_counts = Counter(required_families)
    if hand_size + flop_size < len(required_families):
        raise ValueError("Hand and flop do not contain enough cards for an eight-beat progression.")

    raw_flop_counts = {
        family: required_count * flop_size / len(required_families)
        for family, required_count in required_counts.items()
    }
    flop_counts = {family: int(count) for family, count in raw_flop_counts.items()}
    unassigned_flop_slots = flop_size - sum(flop_counts.values())
    for family in sorted(
        required_counts,
        key=lambda item: raw_flop_counts[item] - flop_counts[item],
        reverse=True,
    )[:unassigned_flop_slots]:
        flop_counts[family] += 1

    family_pools = {
        family: [card for card in deck if family in card.get("familyCompatibility", [])]
        for family in required_counts
    }
    for pool in family_pools.values():
        rng.shuffle(pool)

    used_ids: set[str] = set()

    def draw_card(family: str) -> Dict[str, Any]:
        while family_pools[family]:
            card = family_pools[family].pop()
            if card["id"] not in used_ids:
                used_ids.add(card["id"])
                return card
        raise ValueError(f"Not enough {family} cards to construct progression-ready hands.")

    flop_cards = [
        draw_card(family)
        for family, count in flop_counts.items()
        for _ in range(count)
    ]
    rng.shuffle(flop_cards)

    required_hand_counts = {
        family: required_counts[family] - flop_counts.get(family, 0)
        for family in required_counts
    }
    required_hand_size = sum(required_hand_counts.values())
    if required_hand_size > hand_size:
        raise ValueError("The hand is too small to complement the shared flop progression.")

    hands: List[List[str]] = []
    for _ in range(player_count):
        hand_cards = [
            draw_card(family)
            for family, count in required_hand_counts.items()
            for _ in range(count)
        ]
        filler_families = list(required_families)
        rng.shuffle(filler_families)
        while len(hand_cards) < hand_size:
            hand_cards.append(draw_card(filler_families[(len(hand_cards) - required_hand_size) % len(filler_families)]))
        rng.shuffle(hand_cards)
        hands.append([card["id"] for card in hand_cards])

    remaining = [card for card in deck if card["id"] not in used_ids]
    rng.shuffle(remaining)
    return remaining, hands, [card["id"] for card in flop_cards]


def build_raw_round(
    deck: Sequence[Dict[str, Any]],
    player_count: int,
    hand_size: int,
    flop_size: int,
    rng: random.Random,
) -> Tuple[List[Dict[str, Any]], List[List[str]], List[str]]:
    shuffled_cards = list(deck)
    rng.shuffle(shuffled_cards)
    remaining, hands = deal_hands(shuffled_cards, player_count, hand_size)
    flop_cards = remaining[:flop_size]
    return remaining[flop_size:], hands, [card["id"] for card in flop_cards]


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

    eligible_scores = {player_id: score for player_id, score in scores.items() if isfinite(score)}
    if not eligible_scores:
        winner = ""
        runner_up = None
        round_summary = f"Round judged by {judge} had no legal submissions; no points were awarded."
    else:
        sorted_scores = sorted(eligible_scores.items(), key=lambda item: item[1], reverse=True)
        winner = sorted_scores[0][0]
        runner_up = sorted_scores[1][0] if len(sorted_scores) > 1 else None

        winner_score = scores[winner]
        runner_score = scores[runner_up] if runner_up else None
        round_summary = (
            f"Progression: {objective}. "
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
        hands={player.player_id: list(player.hand) for player in players},
        discards_used={player.player_id: player.discards_used for player in players},
        phrases=phrases,
        scores=scores,
        winner=winner,
        runner_up=runner_up,
        summary=round_summary,
    )


def deal_initial_round(deck: List[Dict[str, Any]], config: GameConfig, rng: random.Random) -> Tuple[List[Dict[str, Any]], List[PlayerState], List[str]]:
    remaining_cards, hands = deal_hands(deck, config.player_count, config.hand_size)
    flop_cards = build_flop(remaining_cards, config.flop_size, rng)
    flop_ids = [card["id"] for card in flop_cards]

    players = [
        PlayerState(player_id=f"P{i + 1}", hand=list(hand))
        for i, hand in enumerate(hands)
    ]
    return remaining_cards, players, flop_ids


def _add_color(el: ET.Element, family: str) -> None:
    el.set("color", COLOR_MAP[family])


def _note_to_pitch(note: Dict[str, Any]) -> ET.Element:
    pitch = ET.Element("pitch")
    ET.SubElement(pitch, "step").text = note["step"]
    alter = note.get("alter", 0)
    if alter != 0:
        ET.SubElement(pitch, "alter").text = str(alter)
    ET.SubElement(pitch, "octave").text = str(note["octave"])
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
        return [{"kind": "pitch", "note": note, "duration": 240, "type": "16th"} for note in notes[:4]]
    if token_type == 9:
        return [{"kind": "pitch", "note": note, "duration": 320, "type": "eighth"} for note in notes[:3]]
    return [{"kind": "rest", "duration": 960, "type": "quarter"}]


def _render_measure_from_cards(
    card_ids: Sequence[str],
    card_map: Dict[str, Dict[str, Any]],
    family: str,
    objective: str,
    measure_number: int,
    include_attributes: bool,
    flop_ids: Sequence[str] = (),
) -> ET.Element:
    measure = ET.Element("measure", {"number": str(measure_number)})

    if include_attributes:
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

    if not card_ids:
        rest_el = ET.SubElement(measure, "note")
        ET.SubElement(rest_el, "rest")
        ET.SubElement(rest_el, "duration").text = "3840"
        ET.SubElement(rest_el, "voice").text = "1"
        ET.SubElement(rest_el, "type").text = "whole"
        _add_color(rest_el, family)
        ET.SubElement(measure, "barline", {"location": "right"})
        return measure

    flop_id_set = set(flop_ids)
    assigned_families = progression_families(objective, family)
    for card_index, card_id in enumerate(card_ids):
        card = card_map[card_id]
        beat_index = (measure_number - 1) * 4 + card_index
        assigned_family = assigned_families[beat_index]
        direction = ET.SubElement(measure, "direction", {"placement": "above"})
        direction_type = ET.SubElement(direction, "direction-type")
        is_flop_card = card_id in flop_id_set
        words_attributes = {"font-weight": "bold", "enclosure": "rectangle"} if is_flop_card else {}
        source_label = "FLOP" if is_flop_card else "HAND"
        ET.SubElement(direction_type, "words", words_attributes).text = (
            f"{source_label}: {card['id']} | {card['rhythm']} | AS {assigned_family}"
        )

        payload = _card_payload(card)
        for item_index, item in enumerate(payload):
            note_el = ET.SubElement(measure, "note")
            if item["kind"] == "rest":
                ET.SubElement(note_el, "rest")
            else:
                note_el.append(_note_to_pitch(item["note"]))
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
            _add_color(note_el, assigned_family)

    ET.SubElement(measure, "barline", {"location": "right"})
    return measure


def _group_phrase_by_measures(phrase_ids: Sequence[str]) -> List[List[str]]:
    return [list(phrase_ids[index:index + 4]) for index in range(0, len(phrase_ids), 4)]


def _append_empty_phrase(part: ET.Element, family: str, objective: str, measure_count: int = 2) -> None:
    for measure_number in range(1, measure_count + 1):
        part.append(
            _render_measure_from_cards(
                [],
                {},
                family,
                objective,
                measure_number,
                include_attributes=measure_number == 1,
            )
        )


def render_phrase_to_musicxml(
    player_id: str,
    round_number: int,
    target_family: str,
    objective: str,
    phrase_ids: Sequence[str],
    card_map: Dict[str, Dict[str, Any]],
    output_path: str | Path,
    flop_ids: Sequence[str] = (),
) -> Path:
    root = ET.Element("score-partwise", {"version": "3.1"})
    work = ET.SubElement(root, "work")
    ET.SubElement(work, "work-title").text = f"Round {round_number} - {target_family} - {objective}"
    part_list = ET.SubElement(root, "part-list")
    score_part = ET.SubElement(part_list, "score-part", {"id": "P1"})
    ET.SubElement(score_part, "part-name").text = f"{player_id} phrase"
    part = ET.SubElement(root, "part", {"id": "P1"})

    if not phrase_ids:
        _append_empty_phrase(part, target_family, objective)
    else:
        measures = _group_phrase_by_measures(phrase_ids)
        for index, measure_card_ids in enumerate(measures, start=1):
            part.append(
                _render_measure_from_cards(
                    measure_card_ids,
                    card_map,
                    target_family,
                    objective,
                    index,
                    include_attributes=index == 1,
                    flop_ids=flop_ids,
                )
            )

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

    all_player_ids = sorted(
        set(round_result.phrases.keys()) | {round_result.judge},
        key=lambda player_id: int(player_id[1:]),
    )

    for player_id in all_player_ids:
        phrase = round_result.phrases.get(player_id, [])
        score_part = ET.SubElement(part_list, "score-part", {"id": player_id})
        player_role = "winner" if player_id == round_result.winner else "judge" if player_id == round_result.judge else "player"
        ET.SubElement(score_part, "part-name").text = f"{player_id} ({player_role})"
        part = ET.SubElement(root, "part", {"id": player_id})

        if not phrase:
            _append_empty_phrase(part, round_result.target_family, round_result.objective)
        else:
            measures = _group_phrase_by_measures(phrase)
            for index, measure_card_ids in enumerate(measures, start=1):
                part.append(
                    _render_measure_from_cards(
                        measure_card_ids,
                        card_map,
                        round_result.target_family,
                        round_result.objective,
                        index,
                        include_attributes=index == 1,
                        flop_ids=round_result.flop,
                    )
                )

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
            flop_ids=round_result.flop,
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
    if config.deal_mode not in {"balanced", "raw"}:
        raise ValueError("deal_mode must be either 'balanced' or 'raw'.")

    rng = random.Random(seed)
    cards = load_deck(deck_path)
    card_map = get_card_map(cards)

    players = [PlayerState(player_id=f"P{i + 1}", hand=[]) for i in range(config.player_count)]
    judge_index = 0
    rounds: List[RoundResult] = []

    for round_number in range(1, config.rounds + 1):
        judge_id = f"P{((judge_index % config.player_count) + 1)}"
        objective_index = (round_number - 1) % len(config.objective_cycle)
        objective = config.objective_cycle[objective_index]
        target_family = progression_resolution_family(objective)

        if config.deal_mode == "balanced":
            remaining_cards, hands, flop_ids = build_progression_ready_round(
                cards,
                objective,
                config.player_count,
                config.hand_size,
                config.flop_size,
                rng,
            )
        else:
            remaining_cards, hands, flop_ids = build_raw_round(
                cards,
                config.player_count,
                config.hand_size,
                config.flop_size,
                rng,
            )

        for idx, hand in enumerate(hands):
            players[idx].hand = list(hand)
            players[idx].discards_used = 0

        for player in players:
            if player.player_id == judge_id:
                continue
            while player.discards_used < config.discard_limit and remaining_cards:
                discard_id = choose_discard(player.hand, card_map, target_family, objective, flop_ids)
                if discard_id is None:
                    break
                player.hand.remove(discard_id)
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

        if export_musicxml_dir is not None:
            export_round_musicxml(round_result, card_map, Path(export_musicxml_dir) / f"round_{round_number:02d}")

    final_scores = {player.player_id: player.score for player in players}
    winner_score = max(final_scores.values())
    tied_winners = [player_id for player_id, score in final_scores.items() if score == winner_score]
    winner_id = rng.choice(tied_winners)
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
    parser.add_argument("--hand-size", type=int, default=6)
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
