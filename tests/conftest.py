"""
Register ymprint's bundled fonts before any test runs, so every test measures
text with the same faces as a real ymprint document (whatever fonts the
machine has, and whichever test happens to import ymprint first).
"""
from ymprint.config.font_registry import register_fonts

register_fonts()
