import logging
from collections.abc import Mapping
from types import MappingProxyType
from typing import ClassVar, override


class ColorFormatter(logging.Formatter):
    COLORS: ClassVar[Mapping[int, str]] = MappingProxyType({
        logging.DEBUG: "\033[36m",     # cyan
        logging.INFO: "\033[32m",      # green
        logging.WARNING: "\033[33m",   # yellow
        logging.ERROR: "\033[31m",     # red
        logging.CRITICAL: "\033[41m",  # red background
    })
    RESET: ClassVar[str] = "\033[0m"

    @override
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, "")
        msg = super().format(record)
        return f"{color}{msg}{self.RESET}" if color else msg

def setup_colored_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(__name__)
    logger.setLevel(level)
    logger.propagate = False  # avoid double logs if root configured elsewhere

    if not logger.handlers:
        h = logging.StreamHandler()
        fmt = "%(asctime)s %(levelname)s %(message)s"
        h.setFormatter(ColorFormatter(fmt))
        logger.addHandler(h)

    return logger

logger = setup_colored_logging(logging.DEBUG)
