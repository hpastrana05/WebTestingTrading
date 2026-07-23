# WebTestingTrading

Private trading lab for personal use: create/run strategies, backtest, tune parameters, and send Telegram alerts. Built to run on a Raspberry Pi 4 with Docker.

## Stack

| Part | Tech |
|------|------|
| Backend | Python, FastAPI, yfinance, pandas, python-telegram-bot |
| Frontend | Next.js (App Router) + React |
| Deploy | Docker Compose |

## Project layout

```
backend/
  app/
    api/           # HTTP routes
    services/      # market data, backtest, tuning, telegram, alerts, rule engine
    strategies/    # builtin strategies + config wrapper
    schemas.py     # request/response models
    config.py      # env settings
    main.py        # FastAPI entrypoint
  data/            # JSON persistence (strategies, alert rules)
  Dockerfile
frontend/
  app/             # Next.js pages
  components/      # Strategy Creator + rule builder
  lib/api.ts       # API client
  Dockerfile
docker-compose.yml
.env.example
```

## Quick start (local)

1. Copy env file and fill Telegram values if you want alerts:

```bash
cp .env.example .env
```

2. Backend:

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

3. Frontend (another terminal):

```bash
cd frontend
npm install
npm run dev
```

UI: http://localhost:3000

## Docker (Raspberry Pi 4)

On the Pi (or any Docker host):

```bash
cp .env.example .env
# edit .env — set TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
# for access from other devices on your LAN, set e.g.:
# NEXT_PUBLIC_API_URL=http://192.168.x.x:8000

docker compose up -d --build
```

- Frontend: `http://<pi-ip>:3000`
- Backend/API: `http://<pi-ip>:8000`
- OpenAPI: `http://<pi-ip>:8000/docs`

Images (`python:3.12-slim`, `node:22-bookworm-slim`) support `linux/arm64`.

## Telegram setup

1. Talk to [@BotFather](https://t.me/BotFather), create a bot, copy the token.
2. Start a chat with the bot, then get your chat id (e.g. via `@userinfobot` or the Bot API `getUpdates`).
3. Put both in `.env`:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

From the Alerts page you can send a test message. Saved rules can be evaluated with:

```bash
curl -X POST http://localhost:8000/api/alerts/check
```

Schedule that endpoint with cron on the Pi if you want periodic checks, for example every weekday at market close.

## Adding a strategy

### Visual creator (recommended)

Open **Strategies → Create strategy**. Configure:

- name, broker ticker, Yahoo ticker, interval, period
- **Entry** and **Exit** rule trees (ALL/ANY, nested groups)
- each condition uses a **pandas-ta** indicator, a price field, or a constant

Saved configs live in `backend/data/strategies.json` and show up in Backtest / Alerts.

### Built-in Python strategies

1. Create a file in `backend/app/strategies/` that subclasses `Strategy`.
2. Implement `generate_signals()` returning `1` (long) or `0` (flat).
3. Register it in `backend/app/strategies/__init__.py`.

Built-in examples: **SMA Crossover** and **RSI Mean Reversion**.

Indicators available in the creator are curated from pandas-ta (`GET /api/indicators`).

## API overview

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/indicators` | pandas-ta indicator catalog |
| GET | `/api/strategies` | List builtin + custom strategies |
| GET/POST/PUT/DELETE | `/api/strategies/configs` | Manage Strategy Creator configs |
| POST | `/api/backtest` | Run a backtest |
| POST | `/api/tuning` | Grid-search parameters (builtins) |
| POST | `/api/alerts/send` | Send a Telegram message |
| GET/POST/PATCH/DELETE | `/api/alerts/rules` | Manage alert rules |
| POST | `/api/alerts/check` | Evaluate rules and notify |

Keep this private on your LAN (or behind a VPN / reverse proxy with auth). Do not expose it to the public internet without protection.
