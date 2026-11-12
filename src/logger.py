"""Application logging configuration for DIT – Invoice Processing Automation."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "invoice_automation.log"


def get_logger(name: str, log_file: Path | str | None = None) -> logging.Logger:
    """Return a configured logger with console and rotating file handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    has_console = any(type(h) is logging.StreamHandler for h in logger.handlers)
    if not has_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    target_log = Path(log_file).resolve() if log_file else DEFAULT_LOG_FILE.resolve()
    existing_log_files = {
        Path(h.baseFilename).resolve()
        for h in logger.handlers
        if isinstance(h, RotatingFileHandler)
    }

    if target_log not in existing_log_files:
        try:
            target_log.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                target_log,
                maxBytes=1_048_576,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError as exc:
            logger.warning(
                "File logging disabled for '%s' (%s); continuing with existing handlers.",
                target_log.name,
                exc,
            )

    return logger
