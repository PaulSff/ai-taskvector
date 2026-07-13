import logging

class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[36m",     # cyan
        logging.INFO: "\033[32m",      # green
        logging.WARNING: "\033[33m",   # yellow
        logging.ERROR: "\033[31m",     # red
        logging.CRITICAL: "\033[41m", # red background
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelno, "")
        msg = super().format(record)
        return f"{color}{msg}{self.RESET}" if color else msg

def setup_colored_logging(level=logging.INFO):
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
