import os
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
APP_BASE_URL = os.getenv("APP_BASE_URL", "").strip().rstrip("/")

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

if not APP_BASE_URL:
    raise RuntimeError("APP_BASE_URL is missing")

app = FastAPI()


@app.get("/")
async def root():
    return {"ok": True, "message": "server works"}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/setup-webhook")
async def setup_webhook():
    webhook_url = f"{APP_BASE_URL}/telegram/webhook"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            json={"url": webhook_url},
        )
        data = response.json()

    return {
        "ok": True,
        "webhook_url": webhook_url,
        "telegram_response": data,
    }


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()
    print("UPDATE:", update)

    message = update.get("message") or update.get("edited_message")
    if not message:
        return JSONResponse({"ok": True})

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return JSONResponse({"ok": True})

    text = message.get("text") or message.get("caption") or "пустое сообщение"

    async with httpx.AsyncClient(timeout=30) as client:
        tg_response = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": f"Ответ: {text}",
            },
        )
        print("SEND MESSAGE:", tg_response.text)

    return JSONResponse({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)