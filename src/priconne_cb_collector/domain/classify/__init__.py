"""Pure classification pipeline for one video (docs/spec/06).

No YouTube / Discord dependencies. Entry point: classify_video().
"""

from __future__ import annotations

from priconne_cb_collector.domain.classify.battle_type import classify_battle_type
from priconne_cb_collector.domain.classify.boss import classify_boss
from priconne_cb_collector.domain.classify.damage import extract_damage
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
    return Classification(
        boss=boss,
        battle_type=battle.battle_type,
        carryover_sec=battle.carryover_sec,
        damage=extract_damage(text),
    )
