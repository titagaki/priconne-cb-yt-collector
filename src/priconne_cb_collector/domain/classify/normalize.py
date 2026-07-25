"""Text normalization shared by all classifiers (docs/spec/06 §1).

NFKC → lowercase → separators to spaces. Katakana is kept as-is.
"""

from __future__ import annotations

import unicodedata

# Separator characters treated as spaces. Includes both raw full-width forms
# (【】「」・ survive NFKC) and the half-width forms NFKC produces.
_SEPARATORS = "【】[]()「」/|-・（）／｜"
_SEP_TABLE = str.maketrans({ch: " " for ch in _SEPARATORS})

DESCRIPTION_HEAD_CHARS = 500  # classification looks at title + first 500 chars


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.lower()
    return text.translate(_SEP_TABLE)


def build_target_text(title: str, description: str | None) -> str:
    """Raw (un-normalized) classification target: title + head of description."""
    head = (description or "")[:DESCRIPTION_HEAD_CHARS]
    return f"{title} {head}"
