from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def root():
    return {"status": "ok", "message": "root works"}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/setup-webhook")
async def setup_webhook():
    return {"status": "ok", "message": "setup-webhook works"}