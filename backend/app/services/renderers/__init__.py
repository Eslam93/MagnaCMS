"""Per-content-type renderers.

Each module exports a pure `render(result) -> str` and a `word_count(text)`
helper. Renderers run once at write time so dashboard preview, full-text
search, copy-to-clipboard, and export all consume the same canonical text.
"""

from app.services.renderers.blog_post import render_blog_post, word_count

__all__ = ["render_blog_post", "word_count"]
