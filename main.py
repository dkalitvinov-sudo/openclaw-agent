from fastapi import FastAPI, Request
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
async def telegram_webhook(request: Request):
    update = await request.json()
    print("UPDATE:", update)

    message = update.get("message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = message.get("text", "нет текста")

    print("CHAT_ID:", chat_id)
    print("TEXT:", text)

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": f"Ответ: {text}"
                },
            )
            print("TELEGRAM RESPONSE:", r.text)
    except Exception as e:
        print("ERROR SENDING:", str(e))

    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)