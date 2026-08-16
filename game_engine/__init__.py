"""Prototype game engine for the tonal phrase card game."""

from .simulator import (
    DEFAULT_DECK_PATH,
    GameConfig,
    GameResult,
    PlayerState,
    RoundResult,
    deal_initial_round,
    load_deck,
    simulate_game,
    validate_phrase,
)

__all__ = [
    "DEFAULT_DECK_PATH",
    "GameConfig",
    "GameResult",
    "PlayerState",
    "RoundResult",
    "deal_initial_round",
    "load_deck",
    "simulate_game",
    "validate_phrase",
]
