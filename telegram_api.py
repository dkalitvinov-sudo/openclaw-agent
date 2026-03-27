from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings


settings = get_settings()


class TelegramAPI:
    def __init__(self) -> None:
        self.base_url = settings.telegram_bot_api_url
        self.file_url = settings.telegram_file_api_url

    async def set_webhook(self, webhook_url: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/setWebhook",
                json={
                    'url': webhook_url,
                    'secret_token': settings.telegram_secret_token,
                    'allowed_updates': ['message', 'edited_message'],
                },
            )
            response.raise_for_status()
            return response.json()

    async def send_message(self, chat_id: int, text: str, reply_to_message_id: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'chat_id': chat_id,
            'text': text[:4096],
        }
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.base_url}/sendMessage", json=payload)
            response.raise_for_status()
            return response.json()

    async def send_chat_action(self, chat_id: int, action: str = 'typing') -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(f"{self.base_url}/sendChatAction", json={'chat_id': chat_id, 'action': action})

    async def send_voice(self, chat_id: int, file_path: str, caption: str | None = None) -> dict[str, Any]:
        data = {'chat_id': str(chat_id)}
        if caption:
            data['caption'] = caption[:1024]
        mime = mimetypes.guess_type(file_path)[0] or 'audio/mpeg'
        async with httpx.AsyncClient(timeout=120) as client:
            with open(file_path, 'rb') as handle:
                files = {'voice': (Path(file_path).name, handle, mime)}
                response = await client.post(f"{self.base_url}/sendVoice", data=data, files=files)
                response.raise_for_status()
                return response.json()

    async def get_file(self, file_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.base_url}/getFile", params={'file_id': file_id})
            response.raise_for_status()
            return response.json()['result']

    async def download_file(self, file_path: str, destination: str) -> str:
        url = f"{self.file_url}/{file_path}"
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(url)
            response.raise_for_status()
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            Path(destination).write_bytes(response.content)
        return destination
