# app/logging_setup.py
import logging, logging.handlers, pathlib, sys

def setup_logging(cfg: dict) -> logging.Logger:
    level_name = str(cfg.get("log_level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    log_dir = pathlib.Path(cfg.get("log_dir", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / str(cfg.get("log_file", "bionews.log"))

    rotate_bytes = int(cfg.get("log_rotate_bytes", 1048576))
    backups = int(cfg.get("log_backups", 5))

    logger = logging.getLogger("bionews")
    logger.setLevel(level)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    # Write to file (rotating)
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=rotate_bytes, backupCount=backups, encoding="utf-8"
    )
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Also echo to console
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(level)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger

class _StreamToLogger:
    """Redirect print() to logger so console == log file."""
    def __init__(self, logger: logging.Logger, level: int):
        self.logger = logger
        self.level = level
        self._buffer = ""

    def write(self, msg):
        if not isinstance(msg, str):
            msg = str(msg)
        self._buffer += msg
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if line:
                self.logger.log(self.level, line)

    def flush(self):
        if self._buffer.strip():
            self.logger.log(self.level, self._buffer.strip())
            self._buffer = ""
