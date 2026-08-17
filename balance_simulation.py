#!/usr/bin/env python3
"""Run reproducible balance sweeps across deal and hand configurations."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path
from statistics import mean, median
from typing import Any, Sequence

from game_engine.simulator import (
    PROGRESSION_TARGETS,
    GameConfig,
    build_progression_ready_round,
    build_raw_round,
    choose_discard,
    count_legal_phrase_selections,
    get_card_map,
    load_deck,
    progression_resolution_family,
    simulate_game,
)


@dataclass(frozen=True)
class Scenario:
    hand_size: int
    flop_size: int
    discard_limit: int

    @property
    def name(self) -> str:
        return f"hand-{self.hand_size}_flop-{self.flop_size}_discards-{self.discard_limit}"


SCENARIOS = (
    Scenario(6, 4, 1),
    Scenario(7, 4, 1),
    Scenario(7, 5, 1),
    Scenario(7, 5, 2),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare raw and progression-balanced game configurations.")
    parser.add_argument("--games", type=int, default=10_000, help="Games to run per mode/configuration scenario.")
    parser.add_argument("--scored-games", type=int, default=25, help="Games per scenario that also run full phrase optimization and scoring.")
    parser.add_argument("--mode", choices=("both", "balanced", "raw"), default="both")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=Path, default=Path("data/balance-report.json"))
    return parser.parse_args()


def _family_selection_ratios(card_map: dict[str, dict[str, Any]], selections: Counter[str]) -> dict[str, float]:
    family_cards: dict[str, list[str]] = defaultdict(list)
    for card_id, card in card_map.items():
        family_cards[card["primaryFamily"]].append(card_id)

    ratios = {}
    for family, card_ids in family_cards.items():
        counts = [selections[card_id] for card_id in card_ids]
        average = mean(counts)
        ratios[family] = round(max(counts) / average, 3) if average else 0.0
    return ratios


def run_scenario(job: tuple[int, int, str, Scenario, int]) -> dict[str, Any]:
    games, scored_games, mode, scenario, starting_seed = job
    cards = load_deck()
    card_map = get_card_map(cards)
    submissions = 0
    legal_submissions = 0
    legal_choices: list[int] = []
    flop_usage: Counter[int] = Counter()
    seat_wins: Counter[str] = Counter()
    objective_scores: dict[str, list[float]] = defaultdict(list)
    objective_legal: Counter[str] = Counter()
    objective_submissions: Counter[str] = Counter()
    selected_cards: Counter[str] = Counter()
    selected_rhythms: Counter[str] = Counter()
    unique_phrases: set[tuple[str, ...]] = set()
    round_margins: list[float] = []
    no_contest_rounds = 0
    tied_games = 0
    completed_games = 0
    scored_legal_submissions = 0

    config = GameConfig(
        rounds=6,
        hand_size=scenario.hand_size,
        flop_size=scenario.flop_size,
        discard_limit=scenario.discard_limit,
        deal_mode=mode,
    )

    rng = random.Random(starting_seed)
    for _ in range(games):
        for round_index in range(config.rounds):
            objective = PROGRESSION_TARGETS[round_index % len(PROGRESSION_TARGETS)]
            target_family = progression_resolution_family(objective)
            judge_index = round_index % config.player_count
            if mode == "balanced":
                remaining, hands, flop = build_progression_ready_round(
                    cards,
                    objective,
                    config.player_count,
                    config.hand_size,
                    config.flop_size,
                    rng,
                )
            else:
                remaining, hands, flop = build_raw_round(
                    cards,
                    config.player_count,
                    config.hand_size,
                    config.flop_size,
                    rng,
                )

            legal_players = 0
            for player_index, hand in enumerate(hands):
                if player_index == judge_index:
                    continue
                discards_used = 0
                while discards_used < config.discard_limit and remaining:
                    discard_id = choose_discard(hand, card_map, target_family, objective, flop)
                    if discard_id is None:
                        break
                    hand.remove(discard_id)
                    hand.append(remaining.pop(0)["id"])
                    discards_used += 1

                choices = count_legal_phrase_selections(hand, flop, card_map, objective, target_family)
                submissions += 1
                objective_submissions[objective] += 1
                objective_legal[objective] += choices > 0
                legal_choices.append(choices)
                if choices > 0:
                    legal_submissions += 1
                    legal_players += 1
            if legal_players == 0:
                no_contest_rounds += 1

    for game_index in range(scored_games):
        result = simulate_game(config=config, seed=starting_seed + games + game_index)
        top_score = max(result.final_scores.values())
        if top_score > 0:
            completed_games += 1
            seat_wins[result.winner] += 1
            tied_games += sum(score == top_score for score in result.final_scores.values()) > 1

        for round_result in result.rounds:
            finite_scores = sorted(
                (score for score in round_result.scores.values() if isfinite(score)),
                reverse=True,
            )
            if len(finite_scores) > 1:
                round_margins.append(finite_scores[0] - finite_scores[1])

            for player_id, phrase in round_result.phrases.items():
                score = round_result.scores[player_id]
                if not isfinite(score):
                    continue

                scored_legal_submissions += 1
                objective_scores[round_result.objective].append(score)
                flop_usage[sum(card_id in round_result.flop for card_id in phrase)] += 1
                unique_phrases.add(tuple(phrase))
                for card_id in phrase:
                    selected_cards[card_id] += 1
                    selected_rhythms[card_map[card_id]["rhythm"]] += 1

    legal_rate = legal_submissions / submissions if submissions else 0.0
    median_choices = float(median(legal_choices)) if legal_choices else 0.0
    objective_mean_scores = {
        objective: round(mean(scores), 3)
        for objective, scores in objective_scores.items()
        if scores
    }
    overall_objective_mean = mean(objective_mean_scores.values()) if objective_mean_scores else 0.0
    objective_spread = (
        (max(objective_mean_scores.values()) - min(objective_mean_scores.values())) / overall_objective_mean
        if objective_mean_scores and overall_objective_mean
        else 0.0
    )
    seat_win_rates = {
        player_id: seat_wins[player_id] / completed_games if completed_games else 0.0
        for player_id in ("P1", "P2", "P3")
    }
    seat_spread = max(seat_win_rates.values()) - min(seat_win_rates.values()) if completed_games else 0.0
    family_ratios = _family_selection_ratios(card_map, selected_cards)
    max_family_ratio = max(family_ratios.values(), default=0.0)
    unused_cards = sum(selected_cards[card_id] == 0 for card_id in card_map)

    return {
        "mode": mode,
        "scenario": asdict(scenario),
        "scenarioName": scenario.name,
        "games": games,
        "scoredGames": scored_games,
        "rounds": games * config.rounds,
        "scoredRounds": scored_games * config.rounds,
        "submissions": submissions,
        "completedGames": completed_games,
        "legalSubmissions": legal_submissions,
        "legalPhraseRate": round(legal_rate, 5),
        "medianLegalSelections": median_choices,
        "meanLegalSelections": round(mean(legal_choices), 3) if legal_choices else 0.0,
        "noContestRounds": no_contest_rounds,
        "noContestRate": round(no_contest_rounds / (games * config.rounds), 5),
        "flopUsage": {str(count): uses for count, uses in sorted(flop_usage.items())},
        "meanFlopUsage": round(
            sum(count * uses for count, uses in flop_usage.items()) / scored_legal_submissions,
            3,
        ) if scored_legal_submissions else 0.0,
        "seatWins": dict(seat_wins),
        "seatWinRates": {player: round(rate, 5) for player, rate in seat_win_rates.items()},
        "tiedGames": tied_games,
        "objectiveMeanScores": objective_mean_scores,
        "objectiveLegalRates": {
            objective: round(objective_legal[objective] / total, 5)
            for objective, total in objective_submissions.items()
        },
        "objectiveScoreSpread": round(objective_spread, 5),
        "meanRoundMargin": round(mean(round_margins), 3) if round_margins else 0.0,
        "uniquePhrases": len(unique_phrases),
        "uniquePhraseRate": round(len(unique_phrases) / scored_legal_submissions, 5) if scored_legal_submissions else 0.0,
        "selectedRhythms": dict(selected_rhythms),
        "unusedCards": unused_cards,
        "maxSelectionRatioByFamily": family_ratios,
        "mostSelectedCards": selected_cards.most_common(10),
        "thresholds": {
            "legalPhraseRateAtLeast90Percent": legal_rate >= 0.90,
            "medianLegalSelectionsBetween3And6": 3 <= median_choices <= 6,
            "seatWinSpreadAtMost8Percent": seat_spread <= 0.08 if completed_games else False,
            "objectiveScoreSpreadAtMost5Percent": objective_spread <= 0.05,
            "maxCardSelectionRatioAtMost2": max_family_ratio <= 2.0,
            "allCardsSelected": unused_cards == 0,
            "meanFlopUsageBetween2And3": 2.0 <= (
                sum(count * uses for count, uses in flop_usage.items()) / scored_legal_submissions
            ) <= 3.0 if scored_legal_submissions else False,
        },
    }


def main() -> None:
    args = parse_args()
    if args.games < 1:
        raise ValueError("--games must be at least 1.")
    if args.scored_games < 1 or args.scored_games > args.games:
        raise ValueError("--scored-games must be between 1 and --games.")
    modes: Sequence[str] = ("balanced", "raw") if args.mode == "both" else (args.mode,)
    jobs = []
    for job_index, (mode, scenario) in enumerate(
        (mode, scenario) for mode in modes for scenario in SCENARIOS
    ):
        jobs.append((args.games, args.scored_games, mode, scenario, args.seed + job_index * args.games))

    workers = max(1, min(args.workers, len(jobs)))
    with ProcessPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(run_scenario, jobs))

    report = {
        "gamesPerScenario": args.games,
        "scoredGamesPerScenario": args.scored_games,
        "totalGames": args.games * len(jobs),
        "totalScoredGames": args.scored_games * len(jobs),
        "modes": list(modes),
        "scenarios": [asdict(scenario) for scenario in SCENARIOS],
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.output} with {report['totalGames']} simulated games.")
    for result in results:
        print(
            f"{result['mode']:8} {result['scenarioName']}: "
            f"legal={result['legalPhraseRate']:.1%}, "
            f"median choices={result['medianLegalSelections']:.1f}, "
            f"no contests={result['noContestRate']:.1%}"
        )


if __name__ == "__main__":
    main()
