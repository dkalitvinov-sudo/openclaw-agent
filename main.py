from __future__ import annotations

import logging
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

from agent import run_agent, synthesize_speech, transcribe_audio
from config import get_settings
from db import init_db
from telegram_api import TelegramAPI

settings = get_settings()
telegram = TelegramAPI()

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)
URL_RE = re.compile(r"https?://\S+")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Telegram Railway Agent", lifespan=lifespan)


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "message": "Telegram Railway Agent is running"}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/setup-webhook")
async def setup_webhook() -> dict[str, Any]:
    webhook_url = f"{settings.app_base_url.rstrip('/')}/telegram/webhook"
    result = await telegram.set_webhook(webhook_url, settings.telegram_secret_token)
    return {"ok": True, "webhook_url": webhook_url, "telegram_result": result}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if settings.telegram_secret_token:
        if x_telegram_bot_api_secret_token != settings.telegram_secret_token:
            raise HTTPException(status_code=401, detail="Invalid secret token")

    update = await request.json()
    await handle_update(update)
    return JSONResponse({"ok": True})


async def handle_update(update: dict[str, Any]) -> None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    user = message.get("from", {})
    user_id = user.get("id")

    if not chat_id or not user_id:
        return

    text = message.get("text") or message.get("caption")
    wants_voice_reply = False

    if text:
        lowered = text.lower()
        wants_voice_reply = "ответь голосом" in lowered or "голосом" in lowered

    if message.get("voice") or message.get("audio"):
        media = message.get("voice") or message.get("audio")
        file_id = media.get("file_id")
        if not file_id:
            return

        file_bytes, suffix = await telegram.download_file_by_id(file_id)

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".ogg") as tmp:
            tmp.write(file_bytes)
            temp_path = tmp.name

        try:
            text = await transcribe_audio(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    if not text:
        await telegram.send_message(chat_id, "Не смог понять сообщение.")
        return

    reply = await run_agent(
        user_id=user_id,
        chat_id=chat_id,
        text=text,
        urls=URL_RE.findall(text),
    )

    if wants_voice_reply:
        voice_bytes = await synthesize_speech(reply)
        await telegram.send_voice(chat_id, voice_bytes)
    else:
        await telegram.send_message(chat_id, reply)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)