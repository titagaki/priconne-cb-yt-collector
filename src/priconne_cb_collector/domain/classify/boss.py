"""Boss classification: name/alias match first, EX notation as fallback.

Spec: docs/spec/06 §2. Pure functions; no YouTube/Discord dependencies.
"""

from __future__ import annotations

import logging
import re

from priconne_cb_collector.domain.classify.normalize import normalize
from priconne_cb_collector.domain.models import (
    MATCH_BOSS_NAME,
    MATCH_EX_NOTATION,
    Boss,
    BossMatch,
)

logger = logging.getLogger(__name__)

SUMMARY_HIT_THRESHOLD = 3  # 3+ boss hits means a compilation video

PRICONNE_CONTEXT_WORDS = ("プリコネ", "クラバト", "クランバトル", "priconne")

# EX notation patterns applied to normalized text (N = 1-5).
# "ex-1" becomes "ex 1" after normalization (separators -> spaces).
_EX_PATTERNS = (
    re.compile(r"(?<![a-z0-9])ex\s?([1-5])(?![0-9])"),
    re.compile(r"(?<![0-9])([1-5])\s?ボス"),
    re.compile(r"ボス\s?([1-5])(?![0-9])"),
    re.compile(r"第\s?([1-5])\s?[ボ弾]"),
)
# Circled digits must be looked up in the RAW text: NFKC folds ① into a
# plain "1", which would be indistinguishable from ordinary digits.
_CIRCLED = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5}


def match_boss_names(raw_text: str, bosses: tuple[Boss, ...]) -> BossMatch:
    """Priority A: substring match on normalized names/aliases."""
    norm = normalize(raw_text)
    indices: list[int] = []
    matched: list[str] = []
    for boss in bosses:
        for alias in boss.aliases:
            if normalize(alias) in norm:
                indices.append(boss.index)
                matched.append(alias)
                break
    if not indices:
        return BossMatch()
    return BossMatch(
        indices=indices,
        match_source=MATCH_BOSS_NAME,
        matched_strings=matched,
        is_summary=len(indices) >= SUMMARY_HIT_THRESHOLD,
    )


def match_ex_notation(raw_text: str) -> tuple[int, str] | None:
    """Return (boss index, matched string) from EX notation, if any."""
    norm = normalize(raw_text)
    for pattern in _EX_PATTERNS:
        m = pattern.search(norm)
        if m:
            return int(m.group(1)), m.group(0)
    for char, index in _CIRCLED.items():
        if char in raw_text:
            return index, char
    return None


def has_priconne_context(raw_text: str) -> bool:
    norm = normalize(raw_text)
    return any(normalize(word) in norm for word in PRICONNE_CONTEXT_WORDS)


def classify_boss(
    raw_text: str,
    bosses: tuple[Boss, ...],
    *,
    enable_ex_notation: bool = True,
    published_in_period: bool = False,
) -> BossMatch:
    """Full boss decision for one video (docs/spec/06 §2).

    EX notation applies only when the name match failed AND the video has
    Priconne context words AND was published within the active period.
    """
    name_match = match_boss_names(raw_text, bosses)
    ex = match_ex_notation(raw_text)

    if name_match.indices:
        if ex is not None and ex[0] not in name_match.indices:
            logger.warning(
                "boss name and EX notation disagree; keeping name match: "
                "name_indices=%s ex_index=%s ex_match=%r",
                name_match.indices,
                ex[0],
                ex[1],
            )
        return name_match

    if (
        enable_ex_notation
        and ex is not None
        and has_priconne_context(raw_text)
        and published_in_period
    ):
        return BossMatch(indices=[ex[0]], match_source=MATCH_EX_NOTATION, matched_strings=[ex[1]])

    return BossMatch()
