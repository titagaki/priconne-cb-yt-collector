"""Pure classification pipeline for one video (docs/spec/06).

No YouTube / Discord dependencies. Entry point: classify_video().
"""

from __future__ import annotations

from priconne_cb_collector.domain.classify.battle_type import classify_battle_type
from priconne_cb_collector.domain.classify.boss import classify_boss
from priconne_cb_collector.domain.classify.metadata import extract_metadata
from priconne_cb_collector.domain.classify.normalize import build_target_text
from priconne_cb_collector.domain.models import Boss, Classification


def classify_video(
    title: str,
    description: str | None,
    bosses: tuple[Boss, ...],
    *,
    enable_ex_notation: bool = True,
    published_in_period: bool = False,
) -> Classification:
    text = build_target_text(title, description)
    boss = classify_boss(
        text,
        bosses,
        enable_ex_notation=enable_ex_notation,
        published_in_period=published_in_period,
    )
    battle = classify_battle_type(text)
    meta = extract_metadata(text)
    return Classification(
        boss=boss,
        battle_type=battle.battle_type,
        carryover_sec=battle.carryover_sec,
        damage=meta.damage,
        is_full_auto=meta.is_full_auto,
        is_manual=meta.is_manual,
        is_training_footage=meta.is_training_footage,
    )
