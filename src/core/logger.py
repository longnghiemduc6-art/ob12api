"""Centralized logging configuration."""
import logging
import sys

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO"):
    """Configure root logger with console output."""
    root = logging.getLogger("ob1")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
        root.addHandler(handler)
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ob1.{name}")


def set_level(level: str):
    """Dynamically change log level."""
    root = logging.getLogger("ob1")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
