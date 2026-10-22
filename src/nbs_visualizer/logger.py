"""统一日志配置：所有模块通过 get_logger(__name__) 获取 logger。"""
import logging
import sys

_CONFIGURED = False


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    root = logging.getLogger("nbs_visualizer")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure_root()
    if not name.startswith("nbs_visualizer"):
        name = f"nbs_visualizer.{name}"
    return logging.getLogger(name)
