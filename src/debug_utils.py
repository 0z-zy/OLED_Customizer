import logging

logger = logging.getLogger("OLED Customizer")
_debug_on = False


def toggle_debug_logging(enabled: bool):
    """Switch the root logger between DEBUG and INFO.

    Never add/remove handlers here: main.py owns the RotatingFileHandler,
    and removing/closing it (the old behavior) silently killed all file
    logging until the next restart.
    """
    global _debug_on
    root_logger = logging.getLogger()
    if enabled:
        root_logger.setLevel(logging.DEBUG)
        _debug_on = True
        logger.info("Debug logging enabled.")
    else:
        if _debug_on:
            logger.info("Debug logging disabled.")
        root_logger.setLevel(logging.INFO)
        _debug_on = False


def is_debug_enabled():
    return _debug_on
