
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
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def align_by_index(entries, count):
    aligned = [None] * count
    if not isinstance(entries, list):
        return aligned

    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue

        index = entry.get("index", position)
        if not isinstance(index, int) or not 0 <= index < count:

            index = position
        if aligned[index] is None:
            aligned[index] = entry

    return aligned


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def generate_json(prompt: str, temperature: float = 0.1, response_schema=None) -> dict:
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
