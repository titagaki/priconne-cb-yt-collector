"""Damage extraction (docs/spec/06 §4). The only optional field we extract."""

from __future__ import annotations

import re

from priconne_cb_collector.domain.classify.normalize import normalize

# 億 optionally followed by a 万 remainder ("2億3000万"), else 万 alone.
_DAMAGE_OKU = re.compile(r"(\d+(?:\.\d+)?)\s?億\s?(?:(\d+)\s?万)?")
_DAMAGE_MAN = re.compile(r"(\d+(?:\.\d+)?)\s?万")


def extract_damage(raw_text: str) -> int | None:
    """Damage in units of 万, or None when nothing parseable is present."""
    norm = normalize(raw_text)
    # commas inside numbers ("2,150万") would break the damage patterns
    norm_numeric = re.sub(r"(?<=\d),(?=\d)", "", norm)

    oku = _DAMAGE_OKU.search(norm_numeric)
    if oku:
        total = float(oku.group(1)) * 10000
        if oku.group(2):
            total += int(oku.group(2))
        return int(round(total))
    man = _DAMAGE_MAN.search(norm_numeric)
    if man:
        return int(round(float(man.group(1))))
    return None
