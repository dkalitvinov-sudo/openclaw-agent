# Telegram Railway Agent

Production-flavored MVP for a Telegram AI agent with:

- Telegram webhook via FastAPI
- OpenAI Responses API with function tools
- Voice message transcription
- Optional voice replies
- Notes, memory, reminders, weather, URL reading
- Railway deployment config

## Project structure

```text
app/
  agent.py         OpenAI orchestration and tool loop
  config.py        settings via environment variables
  db.py            SQLAlchemy models and DB setup
  main.py          FastAPI app and Telegram webhook
  scheduler.py     in-process reminder polling
  telegram_api.py  Telegram Bot API client
  tools.py         custom tools exposed to the model
requirements.txt
railway.toml
.env.example
```

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Then expose the app publicly with a tunnel for local testing, or deploy to Railway and call:

```bash
curl -X POST https://YOUR_APP_URL/setup-webhook
```

## Telegram bot setup

1. Create the bot in `@BotFather`
2. Copy `TELEGRAM_BOT_TOKEN`
3. Set a long random `TELEGRAM_SECRET_TOKEN`
4. Put both into Railway environment variables

## Railway deploy

1. Push this folder to GitHub
2. In Railway, create a new project from GitHub repo
3. Add environment variables from `.env.example`
4. Deploy
5. Open `/setup-webhook` once after the public URL is ready

## Recommended next upgrades

- Add Postgres on Railway and point `DATABASE_URL` to it
- Add Redis + worker for long jobs
- Add confirmation layer for dangerous actions
- Add whitelisted integrations: Gmail, Calendar, Notion, CRM, payments
- Add admin allowlist for personal use only
- Add observability with Sentry and structured logs

## Commands the bot already understands well

- "Запомни, что я люблю короткие ответы"
- "Сохрани заметку: купить микрофон"
- "Найди мои заметки про микрофон"
- "Напомни завтра в 18:30 созвон с Сашей"
- "Какая погода в Киеве?"
- "Ответь голосом: расскажи план на день"

## Important caveats

- The reminder scheduler is in-process. Great for MVP, not ideal for multi-replica production.
- `fetch_url_summary` reads public pages directly and should be wrapped with a safer fetcher for wider use.
- This scaffold does not execute payments, purchases, deletions, or external write actions without you adding them.
