"""Gemini-powered farming chatbot.

The API key is used only on the server.
Conversation history is supplied by chat_routes.py.
"""

import os

from google import genai
from google.genai import types

from utils.i18n import LANG_NAME_FOR_AI


DEFAULT_MODEL = "gemini-3.8-flash"
MAX_HISTORY_MESSAGES = 6
MAX_INPUT_CHARS = 800
MAX_TOKENS = 350

SYSTEM_PROMPT = (
    "You are the Smart Farmer Assistant, a helpful agriculture adviser for farmers in India. "
    "Only answer questions about farming: crops, cultivation, plant diseases, fertilizers, irrigation, "
    "soil management, weather-related farming decisions, farming calendar, mandi prices and "
    "government agricultural schemes. "
    "If a question is about something else, politely say you can only help with farming. "
    "Write in {language}, in simple, beginner-friendly words and short paragraphs. "
    "Safety rules: do NOT name specific pesticide or fungicide products or give chemical doses; "
    "give general guidance and tell the farmer to consult the local agricultural officer or "
    "Krishi Vigyan Kendra for treatment decisions. "
    "Never invent government scheme details, market prices, weather data or statistics; "
    "if you are not sure, say so and point to official sources such as the relevant government portal. "
    "Be honest about uncertainty."
    "Keep answers concise, preferably 3-5 short bullet points. "
    "Avoid unnecessary introductions and repetition."
)


class ChatError(Exception):
    def __init__(self, key):
        super().__init__(key)
        self.key = key


def api_key():
    return os.environ.get("GEMINI_API_KEY", "").strip()


def is_configured():
    return bool(api_key())


def model_name():
    return os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL


def ask(history, user_message, lang="en"):
    """Generate a farming response using Gemini."""

    if not is_configured():
        raise ChatError("chat.not_configured")

    contents = []

    for message in history[-MAX_HISTORY_MESSAGES:]:
        role = "user" if message["role"] == "user" else "model"

        contents.append({
            "role": role,
            "parts": [{"text": message["content"]}]
        })

    contents.append({
        "role": "user",
        "parts": [{"text": user_message}]
    })

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT.format(
            language=LANG_NAME_FOR_AI.get(lang, "English")
        ),
        max_output_tokens=MAX_TOKENS,
        temperature=0.4,
    )

    try:
        client = genai.Client(api_key=api_key())

        response = client.models.generate_content(
            model=model_name(),
            contents=contents,
            config=config,
        )

        text = (response.text or "").strip()

    except Exception as exc:
        status = getattr(exc, "code", None)
        if callable(status):
            status = status()

        if status in (401, 403):
            raise ChatError("chat.auth_error")

        if status == 429:
            raise ChatError("chat.rate_limited")

        raise ChatError("chat.unavailable")

    if not text:
        raise ChatError("chat.unavailable")

    return text

def stream(history, user_message, lang="en"):
    """Yield text chunks from Gemini without storing partial responses."""

    if not is_configured():
        raise ChatError("chat.not_configured")

    contents = []

    for message in history[-MAX_HISTORY_MESSAGES:]:
        role = "user" if message["role"] == "user" else "model"
        contents.append({
            "role": role,
            "parts": [{"text": message["content"]}]
        })

    contents.append({
        "role": "user",
        "parts": [{"text": user_message}]
    })

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT.format(
            language=LANG_NAME_FOR_AI.get(lang, "English")
        ),
        max_output_tokens=MAX_TOKENS,
        temperature=0.4,
    )

    try:
        client = genai.Client(api_key=api_key())

        response_stream = client.models.generate_content_stream(
            model=model_name(),
            contents=contents,
            config=config,
        )

        received_text = False

        for chunk in response_stream:
            text = getattr(chunk, "text", None)
            if text:
                received_text = True
                yield text

        if not received_text:
            raise ChatError("chat.unavailable")

    except ChatError:
        raise
    except Exception as exc:
        status = getattr(exc, "code", None)
        if callable(status):
            status = status()

        if status in (401, 403):
            raise ChatError("chat.auth_error")

        if status == 429:
            raise ChatError("chat.rate_limited")

        raise ChatError("chat.unavailable")