"""起動: 設定を読んで Bot を動かす。"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from priconne_cb_collector.bot import CollectorBot, Paths
from priconne_cb_collector.config import load_bosses, load_config
from priconne_cb_collector.logging_setup import setup_logging
from priconne_cb_collector.store import JST, Store

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="priconne-cb-collector")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path(os.getenv("PRICONNE_CONFIG_DIR", "config")),
        help="config.yaml と bosses.yaml を置くディレクトリ (既定: config)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.getenv("PRICONNE_DB_PATH", "data/bot.db")),
        help="SQLite ファイルのパス (既定: data/bot.db)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path(os.getenv("PRICONNE_LOG_DIR", "logs")),
        help="JSON Lines ログの出力先 (既定: logs)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="設定を読み込んで検証するだけで、Discord へは接続しない",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv()
    setup_logging(os.getenv("LOG_LEVEL", "INFO"), args.log_dir)

    paths = Paths(
        config=args.config_dir / "config.yaml",
        bosses=args.config_dir / "bosses.yaml",
        database=args.db,
    )
    config = load_config(paths.config)
    bosses = load_bosses(paths.bosses)

    current_month = datetime.now(JST).strftime("%Y-%m")
    if bosses.month != current_month:
        logger.warning(
            "bosses.yaml month does not match the current month: bosses=%s current=%s",
            bosses.month,
            current_month,
        )

    if args.check:
        logger.info(
            "config ok: search_interval=%dmin bosses_month=%s boss_channels=%d",
            config.search_interval_minutes,
            bosses.month,
            len(config.boss_channels),
        )
        return 0

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.error("DISCORD_BOT_TOKEN is not set (see .env.example)")
        return 1

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        logger.error("YOUTUBE_API_KEY is not set; nothing can be collected (see .env.example)")
        return 1

    store = Store(paths.database)
    bot = CollectorBot(config, bosses, store, api_key, paths)
    try:
        bot.run(token, log_handler=None)
    finally:
        store.close()
    return 0
