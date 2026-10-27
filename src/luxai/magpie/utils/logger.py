"""Small colored logger for MicroPython consoles."""

import time


class Logger:
    level_order = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
    log_level = "INFO"
    use_color = True
    _colors = {"DEBUG": "\x1b[90m", "INFO": "\x1b[32m",
               "WARN": "\x1b[33m", "ERROR": "\x1b[31m"}

    @classmethod
    def set_level(cls, level):
        level = level.upper()
        if level in cls.level_order:
            cls.log_level = level

    @classmethod
    def set_color(cls, enabled):
        cls.use_color = bool(enabled)

    @classmethod
    def _should_log(cls, level):
        return cls.level_order[level] >= cls.level_order[cls.log_level]

    @staticmethod
    def _timestamp():
        now = time.localtime()
        if now[0] >= 2020:
            return "%04d.%02d.%02d %02d:%02d:%02d" % now[:6]
        # A board without a set RTC should show uptime, not a false date.
        return "+%dms" % time.ticks_ms()

    @classmethod
    def _log(cls, level, message):
        if not cls._should_log(level):
            return
        prefix = "[%s] [%s]:" % (level, cls._timestamp())
        if cls.use_color:
            prefix = cls._colors[level] + prefix + "\x1b[0m"
        print(prefix, message)

    @classmethod
    def debug(cls, message):
        cls._log("DEBUG", message)

    @classmethod
    def info(cls, message):
        cls._log("INFO", message)

    @classmethod
    def warning(cls, message):
        cls._log("WARN", message)

    @classmethod
    def error(cls, message):
        cls._log("ERROR", message)

    @classmethod
    def pretty_print(cls, message):
        if cls._should_log("INFO"):
            import json
            cls.info(json.dumps(message))
