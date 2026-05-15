"""Image-prompt builder.

Mirrors §7.5 of PROJECT_BRIEF.md. Runs as a separate LLM call AFTER
content generation: the model reads the rendered content plus a chosen
style and returns a structured `{ prompt, negative_prompt, style_summary }`
payload. The image provider then consumes that prompt.

Two providers; one schema:

- `gpt-image-1` (OpenAI) takes the positive `prompt` only and folds the
  `negative_prompt` text into it (see service-layer folding).
- Bedrock Nova Canvas takes a real negative prompt. Either way the
  payload shape stays the same — the builder is provider-agnostic.

`PROMPT_VERSION` is persisted on `generated_images.image_prompt` so we
can map a stored image back to the exact builder revision.
"""

from __future__ import annotations

from typing import Any, Final

PROMPT_VERSION: Final[str] = "image_prompt.v1"

SUPPORTED_STYLES: Final[tuple[str, ...]] = (
    "photorealistic",
    "illustration",
    "minimalist",
    "3d_render",
    "watercolor",
    "cinematic",
)

SYSTEM_PROMPT: Final[str] = (
    "You are an expert visual art director who turns marketing copy into "
    "concrete, production-ready image prompts. You output strict JSON: "
    "a positive `prompt`, a `negative_prompt` of things to avoid, and a "
    "short `style_summary` for the dashboard. Never include text or "
    "identifiable people unless the caller explicitly asks."
)

JSON_SCHEMA: Final[dict[str, Any]] = {
    "name": "image_prompt",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["prompt", "negative_prompt", "style_summary"],
        "properties": {
            "prompt": {"type": "string"},
            "negative_prompt": {"type": "string"},
            "style_summary": {"type": "string"},
        },
    },
}


def build_prompt(
    *,
    content_summary: str,
    style: str,
) -> tuple[str, str]:
    """Render (system, user) for the image-prompt builder.

    `content_summary` is the rendered_text of the related content piece
    (or a truncated version of it). `style` must be one of
    `SUPPORTED_STYLES`. The caller is expected to enforce that gate;
    this function trusts its inputs.
    """
    style_line = style if style in SUPPORTED_STYLES else "photorealistic"
    user_prompt = (
        f"Style: {style_line}\n"
        f"Content summary:\n"
        f"---\n"
        f"{content_summary.strip()}\n"
        f"---\n"
        "\n"
        "Produce an image prompt that captures the most concrete visual "
        "metaphor of the content. The image should communicate the "
        "feeling and substance of the copy at a glance — no on-image "
        "text, no logos, no identifiable people.\n"
        "\n"
        "Constraints on the output JSON:\n"
        "- `prompt`: a single paragraph, 30-80 words. Specific subject, "
        "specific composition (e.g. 'isometric three-quarter view'), "
        "specific lighting, specific palette.\n"
        "- `negative_prompt`: comma-separated list of what to exclude — "
        "e.g. 'text, watermark, logos, faces, signatures'. May be empty.\n"
        "- `style_summary`: 4-10 words that describe the chosen direction "
        "(e.g. 'isometric illustration, cool palette').\n"
        "\n"
        "Return ONLY valid JSON matching the supplied schema."
    )
    return SYSTEM_PROMPT, user_prompt


CORRECTIVE_RETRY_INSTRUCTION: Final[str] = (
    "Your previous response was not valid JSON matching the required "
    "schema. Return ONLY valid JSON with keys prompt, negative_prompt, "
    "style_summary. No preamble, no markdown fencing, no explanation."
)
