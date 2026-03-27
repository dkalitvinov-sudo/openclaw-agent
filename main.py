from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
SECRET_TOKEN = os.getenv("TELEGRAM_SECRET_TOKEN", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "alloy")

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

if not APP_BASE_URL:
    raise RuntimeError("APP_BASE_URL is missing")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is missing")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)
app = FastAPI()
URL_RE = re.compile(r"https?://\S+")


async def tg_api(method: str, payload: dict | None = None, files: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    async with httpx.AsyncClient(timeout=60) as http:
        if files:
            response = await http.post(url, data=payload or {}, files=files)
        else:
            response = await http.post(url, json=payload or {})
    response.raise_for_status()
    return response.json()


async def tg_send_message(chat_id: int, text: str) -> None:
    await tg_api("sendMessage", {"chat_id": chat_id, "text": text})


async def tg_send_voice(chat_id: int, voice_bytes: bytes) -> None:
    files = {"voice": ("reply.mp3", voice_bytes, "audio/mpeg")}
    await tg_api("sendVoice", {"chat_id": str(chat_id)}, files=files)


async def tg_get_file(file_id: str) -> tuple[bytes, str]:
    meta = await tg_api("getFile", {"file_id": file_id})
    file_path = meta["result"]["file_path"]
    suffix = Path(file_path).suffix or ".ogg"
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.get(file_url)
        r.raise_for_status()
        return r.content, suffix


async def transcribe_audio(file_path: str) -> str:
    with open(file_path, "rb") as audio_file:
        transcript = await client.audio.transcriptions.create(
            model=OPENAI_TRANSCRIBE_MODEL,
            file=audio_file,
        )

    text = getattr(transcript, "text", None)
    if text:
        return text

    if isinstance(transcript, dict):
        return transcript.get("text", "")

    return ""


async def synthesize_speech(text: str) -> bytes:
    speech = await client.audio.speech.create(
        model=OPENAI_TTS_MODEL,
        voice=OPENAI_TTS_VOICE,
        input=text,
    )
    return speech.read()


async def generate_reply(user_text: str) -> str:
    system_prompt = (
        "Ты полезный Telegram-бот. Отвечай на русском, кратко и понятно. "
        "Если вопрос простой, отвечай прямо. "
        "Не выдумывай действия, которых не совершал."
    )

    response = await client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
    )

    if hasattr(response, "output_text") and response.output_text:
        return response.output_text

    try:
        return response.output[0].content[0].text
    except Exception:
        return "Не смог сформировать ответ."


@app.get("/")
async def root():
    return {"status": "ok", "message": "telegram bot server works"}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/setup-webhook")
async def setup_webhook():
    webhook_url = f"{APP_BASE_URL}/telegram/webhook"
    payload = {"url": webhook_url}
    if SECRET_TOKEN:
        payload["secret_token"] = SECRET_TOKEN

    result = await tg_api("setWebhook", payload)
    return {"ok": True, "webhook_url": webhook_url, "telegram_response": result}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if SECRET_TOKEN and x_telegram_bot_api_secret_token != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid secret token")

    update = await request.json()
    print("UPDATE:", update)

    message = update.get("message") or update.get("edited_message")
    if not message:
        return JSONResponse({"ok": True})

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    if not chat_id:
        return JSONResponse({"ok": True})

    text = message.get("text") or message.get("caption")
    wants_voice_reply = False

    if text:
        lowered = text.lower()
        wants_voice_reply = "голосом" in lowered or "voice" in lowered

    if message.get("voice") or message.get("audio"):
        media = message.get("voice") or message.get("audio")
        file_id = media.get("file_id")

        if file_id:
            file_bytes, suffix = await tg_get_file(file_id)

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".ogg") as tmp:
                tmp.write(file_bytes)
                temp_path = tmp.name

            try:
                text = await transcribe_audio(temp_path)
            finally:
                Path(temp_path).unlink(missing_ok=True)

    if not text:
        await tg_send_message(chat_id, "Не смог понять сообщение.")
        return JSONResponse({"ok": True})

    print("TEXT:", text)
    reply = await generate_reply(text)
    print("REPLY:", reply)

    if wants_voice_reply:
        voice_bytes = await synthesize_speech(reply)
        await tg_send_voice(chat_id, voice_bytes)
    else:
        await tg_send_message(chat_id, reply)

    return JSONResponse({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)