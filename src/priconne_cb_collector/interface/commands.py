"""Slash commands (docs/spec/09).

/start and /collect require an explicit confirmation button: /start because
posting with a stale bosses.yaml is the failure mode this bot is designed to
prevent, /collect because it spends API quota.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import discord
from discord import app_commands

from priconne_cb_collector.adapters.sqlite_store import STATUS_POSTED
from priconne_cb_collector.adapters.youtube_api import SEARCH_COST
from priconne_cb_collector.domain.models import PHASE_BATTLE, PHASE_IDLE, PHASE_TRAINING
from priconne_cb_collector.domain.schedule import JST
from priconne_cb_collector.domain.settings import MODE_TRIGGER
from priconne_cb_collector.interface.embeds import NOTICE_COLOR

logger = logging.getLogger(__name__)

PHASE_LABELS = {
    PHASE_IDLE: "待機中 (idle)",
    PHASE_TRAINING: "トレーニング期間 (training)",
    PHASE_BATTLE: "クラバト本番 (battle)",
}


class ConfirmView(discord.ui.View):
    """A yes/no gate. Only the invoking user may answer."""

    def __init__(self, user_id: int, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.confirmed: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "このボタンはコマンドを実行した本人のみ操作できます。", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="実行する", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="やめる", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        await interaction.response.defer()
        self.stop()

    async def on_timeout(self) -> None:
        self.confirmed = False


def setup_commands(bot) -> None:
    """Register every slash command against the bot's command tree."""
    tree = bot.tree

    @tree.command(name="status", description="現在のフェーズと収集状況を表示します")
    async def status(interaction: discord.Interaction):
        now = datetime.now(UTC)
        period = bot.current_period()
        phase = bot.current_phase(now)

        embed = discord.Embed(title="Bot ステータス", color=NOTICE_COLOR)
        embed.add_field(name="フェーズ", value=PHASE_LABELS.get(phase, phase), inline=False)
        embed.add_field(name="稼働モード", value=bot.config.schedule.mode, inline=True)
        embed.add_field(name="ボス構成", value=bot.bosses.month, inline=True)

        if period is None:
            embed.add_field(
                name="次の遷移",
                value="`/start` で稼働を開始してください（trigger モード）"
                if bot.config.schedule.mode == MODE_TRIGGER
                else "期間が未設定です",
                inline=False,
            )
        else:
            embed.add_field(name="次の遷移", value=_next_transition(now, period), inline=False)
            counts = bot.store.count_by_boss(period.cb_period)
            lines = []
            for boss in bot.bosses.bosses:
                lines.append(f"{boss.index}ボス {boss.name}: {counts.get(boss.index, 0)}件")
            unknown = counts.get(None, 0)
            if unknown:
                lines.append(f"判定できず: {unknown}件")
            embed.add_field(name="収集件数", value="\n".join(lines) or "なし", inline=False)

        used = bot.store.quota_used(now)
        limit = bot.config.youtube.quota_limit_per_day
        embed.add_field(name="クォータ", value=f"{used} / {limit} ユニット使用", inline=False)
        await interaction.response.send_message(embed=embed)

    @tree.command(name="bosses", description="設定中のボス一覧を表示します")
    async def bosses_cmd(interaction: discord.Interaction):
        await interaction.response.send_message(embed=bot.bosses_embed())

    @tree.command(name="recent", description="直近の収集結果を表示します")
    @app_commands.describe(boss="ボス番号 (1-5)。省略時は全ボス")
    async def recent(interaction: discord.Interaction, boss: int | None = None):
        period = bot.current_period()
        if period is None:
            await interaction.response.send_message("稼働期間が未設定です。", ephemeral=True)
            return
        rows = bot.store.recent_videos(period.cb_period, boss_index=boss, limit=10)
        if not rows:
            await interaction.response.send_message(
                "収集済みの動画はまだありません。", ephemeral=True
            )
            return

        embed = discord.Embed(title="直近の収集結果", color=NOTICE_COLOR)
        for row in rows:
            status_label = {
                "pending": "投稿待ち",
                STATUS_POSTED: "投稿済み",
                "filtered": f"除外 ({row['filter_reason']})",
                "error": "エラー",
            }.get(row["status"], row["status"])
            boss_label = f"{row['boss_index']}ボス" if row["boss_index"] else "判定できず"
            embed.add_field(
                name=row["title"][:100],
                value=f"{boss_label} ・ {status_label}\nhttps://www.youtube.com/watch?v={row['video_id']}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @tree.command(name="start", description="[管理者] 稼働を即時開始します")
    @app_commands.default_permissions(administrator=True)
    async def start(interaction: discord.Interaction):
        view = ConfirmView(interaction.user.id)
        embed = bot.bosses_embed()
        embed.description = (
            "**この構成で収集を開始します。**\n"
            "毎月ボスは入れ替わります。内容が今月のものか確認してください。"
        )
        await interaction.response.send_message(embed=embed, view=view)
        await view.wait()

        if not view.confirmed:
            await interaction.followup.send("開始をキャンセルしました。", ephemeral=True)
            return

        period = await bot.start_period(datetime.now(UTC))
        await interaction.followup.send(f"収集を開始しました（対象期間 {period.cb_period}）。")

    @tree.command(name="stop", description="[管理者] 稼働を停止し idle に戻します")
    @app_commands.default_permissions(administrator=True)
    async def stop(interaction: discord.Interaction):
        stopped = bot.stop_period()
        if stopped:
            await interaction.response.send_message(
                "稼働を停止しました。収集済みデータは保持されます。"
            )
        else:
            await interaction.response.send_message("現在稼働していません。", ephemeral=True)

    @tree.command(name="reload", description="[管理者] 設定ファイルを再読込します")
    @app_commands.default_permissions(administrator=True)
    async def reload(interaction: discord.Interaction):
        try:
            bot.reload_config()
        except Exception as exc:
            await interaction.response.send_message(f"再読込に失敗しました: {exc}", ephemeral=True)
            return
        await interaction.response.send_message(embed=bot.bosses_embed())

    @tree.command(name="collect", description="[管理者] 手動で収集を1回実行します")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(api_search="API 検索も実行する（クォータを消費します）")
    async def collect(interaction: discord.Interaction, api_search: bool = False):
        if bot.current_phase() == PHASE_IDLE:
            await interaction.response.send_message(
                "稼働期間外です。先に `/start` を実行してください。", ephemeral=True
            )
            return

        planned = SEARCH_COST * len(bot.bosses.bosses) if api_search else 0
        used = bot.store.quota_used()
        view = ConfirmView(interaction.user.id)
        embed = discord.Embed(title="手動収集の確認", color=0xF1C40F)
        embed.add_field(
            name="RSS 巡回",
            value=f"{len(bot.config.youtube.channels)}チャンネル（0ユニット）",
            inline=False,
        )
        embed.add_field(
            name="API 検索",
            value=f"実行する（約{planned}ユニット）" if api_search else "実行しない",
            inline=False,
        )
        embed.add_field(
            name="本日のクォータ",
            value=f"{used} / {bot.config.youtube.quota_limit_per_day} ユニット使用済み",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, view=view)
        await view.wait()

        if not view.confirmed:
            await interaction.followup.send("収集をキャンセルしました。", ephemeral=True)
            return

        result = await bot.run_collection(run_api_search=api_search)
        await interaction.followup.send(
            f"収集完了: 取得 {result.fetched}件 / 新規 {result.new}件 / "
            f"投稿待ち {result.pending}件 / 除外 {result.filtered}件 / "
            f"エラー {result.errors}件 / クォータ消費 {result.quota_used}ユニット"
        )

    period_group = app_commands.Group(
        name="period",
        description="[管理者] 稼働期間の操作",
        default_permissions=discord.Permissions(administrator=True),
    )

    @period_group.command(
        name="set", description="トレモ開始 / 本番開始 / 終了日を手動で上書きします"
    )
    @app_commands.describe(
        training_start="トレモ開始日 (YYYY-MM-DD)",
        battle_start="本番開始日 (YYYY-MM-DD)",
        end="終了日 (YYYY-MM-DD、この日を含む)",
    )
    async def period_set(
        interaction: discord.Interaction,
        battle_start: str,
        end: str,
        training_start: str | None = None,
    ):
        try:
            period = bot.set_manual_period(training_start, battle_start, end)
        except Exception as exc:
            await interaction.response.send_message(
                f"日付の解釈に失敗しました: {exc}", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "manual モードに切り替えました。\n"
            f"トレモ開始: {period.training_start.astimezone(JST):%Y-%m-%d %H:%M}\n"
            f"本番開始: {period.battle_start.astimezone(JST):%Y-%m-%d %H:%M}\n"
            f"終了: {period.battle_end.astimezone(JST):%Y-%m-%d %H:%M}"
        )

    tree.add_command(period_group)

    @tree.command(
        name="suggest_channels",
        description="[管理者] RSS 監視候補のチャンネルを提案します（クォータ消費なし）",
    )
    @app_commands.default_permissions(administrator=True)
    async def suggest_channels(interaction: discord.Interaction):
        monitored = {c.id for c in bot.config.youtube.channels}
        rows = bot.store.channel_hit_counts(monitored, limit=10)
        if not rows:
            await interaction.response.send_message(
                "提案できるチャンネルがありません。収集データが溜まってから実行してください。",
                ephemeral=True,
            )
            return

        lines = [
            f"{i}. **{row['channel_title'] or '(名称不明)'}** — {row['hits']}件\n"
            f"`{row['channel_id']}`"
            for i, row in enumerate(rows, start=1)
        ]
        embed = discord.Embed(
            title="RSS 監視候補",
            description="\n".join(lines),
            color=NOTICE_COLOR,
        )
        embed.set_footer(text="config.yaml の youtube.channels に追記して /reload してください")
        await interaction.response.send_message(embed=embed)


def _next_transition(now: datetime, period) -> str:
    if now < period.training_start:
        return f"トレーニング開始: {period.training_start.astimezone(JST):%Y-%m-%d %H:%M}"
    if now < period.battle_start:
        return f"本番開始: {period.battle_start.astimezone(JST):%Y-%m-%d %H:%M}"
    if now <= period.battle_end:
        return f"終了: {period.battle_end.astimezone(JST):%Y-%m-%d %H:%M}"
    return "この期間は終了しました"
