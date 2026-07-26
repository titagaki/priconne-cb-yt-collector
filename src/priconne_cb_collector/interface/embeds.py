"""Embed construction (docs/spec/08 §2).

The video description is never reproduced: title, link and derived labels only.
"""

from __future__ import annotations

from datetime import datetime

import discord

from priconne_cb_collector.domain.models import (
    BATTLE_CARRYOVER,
    MATCH_EX_NOTATION,
    BossesConfig,
)
from priconne_cb_collector.domain.schedule import JST

VIDEO_URL = "https://www.youtube.com/watch?v={video_id}"
THUMBNAIL_URL = "https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

# Fixed per-boss colors, keyed by index.
BOSS_COLORS = {
    1: 0xE74C3C,
    2: 0xE67E22,
    3: 0xF1C40F,
    4: 0x2ECC71,
    5: 0x3498DB,
}
UNKNOWN_COLOR = 0x95A5A6
NOTICE_COLOR = 0x5865F2

BATTLE_TYPE_LABELS = {
    "normal": "通常",
    BATTLE_CARRYOVER: "持ち越し",
    "unknown": "不明",
}


def build_video_embed(row, bosses: BossesConfig) -> discord.Embed:
    """Build the embed for one stored video row."""
    color = BOSS_COLORS.get(row["boss_index"], UNKNOWN_COLOR)
    embed = discord.Embed(
        title=row["title"][:256],
        url=VIDEO_URL.format(video_id=row["video_id"]),
        color=color,
    )
    embed.set_image(url=THUMBNAIL_URL.format(video_id=row["video_id"]))

    embed.add_field(name="ボス", value=boss_label(row, bosses), inline=True)
    embed.add_field(name="種別", value=battle_type_label(row), inline=True)
    if row["damage"]:
        embed.add_field(name="ダメージ", value=f"{row['damage']:,}万", inline=True)

    embed.set_footer(text=" ・ ".join(_footer_parts(row)))
    return embed


def _footer_parts(row) -> list[str]:
    """Only what the video title does not already say (docs/spec/08 §2)."""
    parts = [row["channel_title"] or "不明なチャンネル", jst_label(row["published_at"])]
    if row["match_source"] == MATCH_EX_NOTATION:
        parts.append("※EX表記から推定")
    return parts


def boss_label(row, bosses: BossesConfig) -> str:
    if row["boss_index"]:
        boss = bosses.by_index(row["boss_index"])
        return f"{boss.index}ボス {boss.name}"
    return "判定できず"


def battle_type_label(row) -> str:
    label = BATTLE_TYPE_LABELS.get(row["battle_type"], "不明")
    if row["battle_type"] == BATTLE_CARRYOVER and row["carryover_sec"]:
        return f"{label} ({row['carryover_sec']}秒)"
    return label


def jst_label(published_at_utc: str) -> str:
    return datetime.fromisoformat(published_at_utc).astimezone(JST).strftime("%m/%d %H:%M")


def build_bosses_embed(bosses: BossesConfig, current_month: str) -> discord.Embed:
    """The boss roster, shown by /start and /reload."""
    embed = discord.Embed(title="今月のボス構成", color=NOTICE_COLOR)
    embed.add_field(name="対象月", value=bosses.month, inline=False)
    for boss in bosses.bosses:
        embed.add_field(
            name=f"{boss.index}ボス",
            value=f"**{boss.name}**\n別名: {'、'.join(boss.aliases)}",
            inline=False,
        )
    if bosses.month != current_month:
        embed.set_footer(
            text=f"⚠️ bosses.yaml の month ({bosses.month}) が当月 ({current_month}) と一致しません"
        )
    return embed
