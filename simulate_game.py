#!/usr/bin/env python3
"""Run a prototype simulation of the tonal phrase card game."""

import argparse

from game_engine.simulator import GameConfig, simulate_game


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate a prototype tonal phrase card game and optionally export MusicXML phrase files.")
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
    result = simulate_game(config=config, seed=args.seed, export_musicxml_dir=args.export_musicxml)
    print(result.summary)
    print()
    for round_result in result.rounds:
        print(f"Round {round_result.round_number}: {round_result.summary}")
