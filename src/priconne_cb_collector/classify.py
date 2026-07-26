"""どのチャンネルに投げるかを決めるための最小限の判定。

Boss names are already in the search query; matching them again here only
decides which channel a video goes to. Nothing else is extracted.
"""

from __future__ import annotations

import unicodedata

from priconne_cb_collector.config import Boss

# Separator characters treated as spaces. Includes both raw full-width forms
# (【】「」・ survive NFKC) and the half-width forms NFKC produces.
_SEPARATORS = "【】[]()「」/|-・（）／｜"
_SEP_TABLE = str.maketrans({ch: " " for ch in _SEPARATORS})


def normalize(text: str) -> str:
    """NFKC → lowercase → separators to spaces. Katakana is kept as-is."""
    return unicodedata.normalize("NFKC", text or "").lower().translate(_SEP_TABLE)


def match_boss(title: str, bosses: tuple[Boss, ...]) -> int | None:
    """Boss index for the title, or None when it cannot be decided.

    Undecided covers both "no boss name found" and "several found": a video
    naming two bosses belongs to neither channel. Those go to the fallback.
    """
    norm = normalize(title)
    hits = [
        boss.index
        # name is always a candidate: aliases supplement it, they don't replace it.
        for boss in bosses
        if any(normalize(alias) in norm for alias in (boss.name, *boss.aliases))
    ]
    return hits[0] if len(hits) == 1 else None


def is_ng(title: str, ng_words: tuple[str, ...]) -> bool:
    """Plain substring match on the raw title (docs/spec/04 §3)."""
    return any(word in title for word in ng_words)
