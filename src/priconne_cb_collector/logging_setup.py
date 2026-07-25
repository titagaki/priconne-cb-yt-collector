"""Structured logging: JSON Lines to file, plain text to stderr (docs/spec/10 §2)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonLinesFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", log_dir: str | Path = "logs") -> None:
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()

    file_handler = logging.FileHandler(log_dir / "bot.jsonl", encoding="utf-8")
    file_handler.setFormatter(JsonLinesFormatter())
    root.addHandler(file_handler)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(console)

    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
