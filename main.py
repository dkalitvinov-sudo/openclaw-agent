from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
import httpx
import uvicorn
from config import get_settings

settings = get_settings()
app = FastAPI()


@app.get("/")
async def root():
    return {"status": "ok", "message": "bot server works"}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/setup-webhook")
async def setup_webhook():
    webhook_url = f"{settings.app_base_url.rstrip('/')}/telegram/webhook"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
            json={"url": webhook_url},
        )

    return {
        "ok": True,
        "webhook_url": webhook_url,
        "telegram_response": response.json(),
    }


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if settings.telegram_secret_token:
        if x_telegram_bot_api_secret_token != settings.telegram_secret_token:
            raise HTTPException(status_code=401, detail="Invalid secret token")

    update = await request.json()
    message = update.get("message") or update.get("edited_message")

    if not message:
        return JSONResponse({"ok": True})

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text") or message.get("caption") or "Сообщение получено."

    if chat_id:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": f"Ты написал: {text}",
                },
            )

    return JSONResponse({"ok": True})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)