"""Shared Gemini access for the agent modules.

Every agent needs the same three things: an API key check, a client, and a reply
parsed as JSON. Keeping that in one place means the retry policy, the model name
and the code-fence handling are defined once instead of four times.

Each agent still owns its own prompt and its own fallback behaviour.
"""

import json
import logging
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

logger = logging.getLogger(__name__)

# Overridable so the model can be swapped on a deployment without a code change.
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
MAX_ATTEMPTS = 3

_client = None


def ensure_api_key() -> None:
    """Raise if the key is missing, so the caller fails loudly instead of quietly."""
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY environment variable is not set. Please configure it.")


def get_client() -> genai.Client:
    """One client for the whole process; it is safe to reuse."""
    ensure_api_key()
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def as_bool(value) -> bool:
    """Read a boolean out of a model response without being fooled by strings.

    Agent replies are parsed JSON, not a validated schema, so a model answering
    with the string "false" is normal. ``bool("false")`` is True in Python, which
    would turn a "not supported" verdict into a confirmation - the opposite of
    failing closed.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def _strip_code_fence(text: str) -> str:
    """Models sometimes wrap JSON in ```json ... ``` despite being asked not to."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def generate_json(prompt: str, temperature: float = 0.1, response_schema=None) -> dict:
    """Send a prompt to Gemini and return the reply parsed as a dict.

    Retries with a short backoff, because the API occasionally returns 503 or
    rate-limit errors that succeed on a second attempt. Raises RuntimeError if
    every attempt fails, so each agent can fall back in its own way.
    """
    client = get_client()

    config = {"temperature": temperature}
    if response_schema is not None:
        config["response_mime_type"] = "application/json"
        config["response_schema"] = response_schema

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(**config),
            )
            return json.loads(_strip_code_fence(response.text))
        except Exception as error:
            last_error = error
            logger.warning(
                "Gemini call failed (attempt %s/%s): %s", attempt, MAX_ATTEMPTS, error
            )
            if attempt < MAX_ATTEMPTS:
                time.sleep(2**attempt)

    raise RuntimeError(f"Gemini call failed after {MAX_ATTEMPTS} attempts: {last_error}")
