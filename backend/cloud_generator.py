"""
cloud_generator.py — Free cloud image generation via Pollinations.ai (Flux).

The backend generates the URL; the browser loads the image directly from Pollinations.
Completely free, no API key, no signup. Rate limited to 1 concurrent per client IP.
"""

from urllib.parse import quote


def build_url(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    seed: str = "",
) -> str:
    import uuid
    s = seed or str(uuid.uuid4().int % (2**31))
    encoded = quote(prompt, safe="")
    return f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&model=flux&seed={s}"
