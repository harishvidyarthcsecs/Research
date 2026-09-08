"""Shared research-result serialization and report rendering."""

from .report_builder import build_report_dict, detect_run_mode, render_markdown

__all__ = ["build_report_dict", "detect_run_mode", "render_markdown"]
