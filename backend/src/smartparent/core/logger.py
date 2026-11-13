"""
STUDIQS® SmartParent™ (v6.2 Complete) - Structured Logging Subsystem
Outputs formatted, timestamped log messages with module source and severity.
"""

import logging
import sys
from typing import Any, Dict


class StructuredFormatter(logging.Formatter):
    """Clean structured log formatter with timestamp, level, and module name."""
    
    def format(self, record: logging.LogRecord) -> str:
        record_dict: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            record_dict["exc_info"] = self.formatException(record.exc_info)
        return f"[{record_dict['timestamp']}] [{record_dict['level']}] [{record_dict['module']}]: {record_dict['message']}"


def setup_logger(name: str = "smartparent", level: int = logging.INFO) -> logging.Logger:
    """Configures and returns a centralized structured logger."""
    log = logging.getLogger(name)
    if not log.handlers:
        log.setLevel(level)
        # Ensure utf-8 encoding on Windows console
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = StructuredFormatter(datefmt="%Y-%m-%d %H:%M:%S")
        handler.setFormatter(formatter)
        log.addHandler(handler)
        log.propagate = False
    return log


logger = setup_logger()
