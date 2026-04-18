import logging
import os
import json
import io
import shutil
from datetime import datetime

# Global buffer to hold logs in memory
_LOG_BUFFER = io.StringIO()

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        if hasattr(record, "props"):
            log_entry.update(record.props)
        return json.dumps(log_entry)

def setup_logger(log_dir="logs", log_level="INFO"):
    # CLEANUP: Delete local logs directory entirely (Cloud-only mode)
    if os.path.exists(log_dir):
        try:
            shutil.rmtree(log_dir)
        except Exception:
            pass

    logger = logging.getLogger("backup_engine")
    logger.setLevel(log_level)
    
    if logger.handlers:
        return logger

    formatter = JsonFormatter()

    # Memory Handler: Captures all logs for Cloud Sync
    memory_handler = logging.StreamHandler(_LOG_BUFFER)
    memory_handler.setFormatter(formatter)
    logger.addHandler(memory_handler)

    # Console Handler: Warnings/Errors only
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    logger.addHandler(console)

    return logger

def get_log_content():
    """Returns the accumulated logs from memory."""
    return _LOG_BUFFER.getvalue()

def get_logger():
    return logging.getLogger("backup_engine")
