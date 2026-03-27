from __future__ import annotations

import logging
import os
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from agent import run_agent, synthesize_speech, transcribe_audio
from config import get_settings
from db import SessionLocal, init_db
from scheduler import start_scheduler
from telegram_api import TelegramAPI


settings = get_settings()
telegram = TelegramAPI()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)
URL_RE = re.compile(r'https?://\S+')


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    start_scheduler()
    yield


app = FastAPI(title='Telegram Railway Agent', lifespan=lifespan)


@app.get('/healthz')
async def healthz() -> dict[str, str]:
    return {'status': 'ok'}


@app.post('/telegram/webhook')
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)) -> JSONResponse:
    if x_telegram_bot_api_secret_token != settings.telegram_secret_token:
        raise HTTPException(status_code=401, detail='bad secret token')

    update = await request.json()
    message = update.get('message') or update.get('edited_message')
    if not message:
        return JSONResponse({'ok': True})

    chat = message.get('chat') or {}
    from_user = message.get('from') or {}
    chat_id = chat.get('id')
    user_id = from_user.get('id')
    message_id = message.get('message_id')

    if not chat_id or not user_id:
        return JSONResponse({'ok': True})

    await telegram.send_chat_action(chat_id, 'typing')

    text = await extract_user_text(message)
    if not text:
        await telegram.send_message(chat_id, 'Ð¯ Ð¿Ð¾ÐºÐ° Ð¿Ð¾Ð½Ð¸Ð¼Ð°Ñ ÑÐµÐºÑÑ, Ð³Ð¾Ð»Ð¾ÑÐ¾Ð²ÑÐµ Ð¸ ÑÑÑÐ»ÐºÐ¸. ÐÐ¾Ð¿ÑÐ¾Ð±ÑÐ¹ Ð¾ÑÐ¿ÑÐ°Ð²Ð¸ÑÑ ÑÐ¾Ð¾Ð±ÑÐµÐ½Ð¸Ðµ ÐµÑÑ ÑÐ°Ð·.')
        return JSONResponse({'ok': True})

    try:
        async with SessionLocal() as session:
            reply = await run_agent(session, user_id=user_id, chat_id=chat_id, text=text)
        if wants_voice_reply(text):
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = str(Path(tmpdir) / 'reply.mp3')
                await synthesize_speech(reply, output_path)
                await telegram.send_voice(chat_id, output_path, caption=reply[:1024])
        else:
            await telegram.send_message(chat_id, reply, reply_to_message_id=message_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception('Failed to process message: %s', exc)
        await telegram.send_message(chat_id, 'Ð£Ð¿Ñ. Ð§ÑÐ¾-ÑÐ¾ ÑÐ¿Ð¾ÑÐºÐ½ÑÐ»Ð¾ÑÑ Ð½Ð° ÑÐµÑÐ²ÐµÑÐµ. ÐÑÐ¾Ð²ÐµÑÑ Ð»Ð¾Ð³Ð¸ Railway Ð¸ Ð¿Ð¾Ð¿ÑÐ¾Ð±ÑÐ¹ ÐµÑÑ ÑÐ°Ð·.')

    return JSONResponse({'ok': True})


@app.post('/setup-webhook')
async def setup_webhook() -> dict[str, Any]:
    if not settings.app_base_url:
        raise HTTPException(status_code=400, detail='APP_BASE_URL is required')
    webhook_url = settings.app_base_url.rstrip('/') + '/telegram/webhook'
    result = await telegram.set_webhook(webhook_url)
    return {'webhook_url': webhook_url, 'telegram_result': result}


async def extract_user_text(message: dict[str, Any]) -> str | None:
    if message.get('text'):
        return message['text']
    if message.get('caption'):
        return message['caption']
    if message.get('voice'):
        return await transcribe_telegram_file(message['voice']['file_id'], suffix='.ogg')
    if message.get('audio'):
        file_name = message['audio'].get('file_name', 'audio.mp3')
        suffix = Path(file_name).suffix or '.mp3'
        return await transcribe_telegram_file(message['audio']['file_id'], suffix=suffix)
    if message.get('document'):
        name = message['document'].get('file_name', '')
        match = URL_RE.search(name)
        if match:
            return f'ÐÑÐ¾ÑÐ¸ÑÐ°Ð¹ Ð¸ ÐºÑÐ°ÑÐºÐ¾ Ð¿ÐµÑÐµÑÐºÐ°Ð¶Ð¸: {match.group(0)}'
    return None


async def transcribe_telegram_file(file_id: str, suffix: str) -> str:
    file_meta = await telegram.get_file(file_id)
    size = file_meta.get('file_size') or 0
    if size > settings.max_file_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f'File exceeds {settings.max_file_mb} MB limit')
    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = str(Path(tmpdir) / f'input{suffix}')
        await telegram.download_file(file_meta['file_path'], local_path)
        return await transcribe_audio(local_path)


def wants_voice_reply(text: str) -> bool:
    lowered = text.lower()
    triggers = ['Ð¾ÑÐ²ÐµÑÑ Ð³Ð¾Ð»Ð¾ÑÐ¾Ð¼', 'Ð³Ð¾Ð»Ð¾ÑÐ¾Ð¼ Ð¾ÑÐ²ÐµÑÑ', 'voice reply', 'send voice']
    return any(trigger in lowered for trigger in triggers)
