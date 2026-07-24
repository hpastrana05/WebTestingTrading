from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.services.telegram_bot import start_telegram_bot, stop_telegram_bot


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await start_telegram_bot()
    try:
        yield
    finally:
        await stop_telegram_bot()


app = FastAPI(
    title="WebTestingTrading API",
    description="Private trading lab: strategies, backtesting, tuning, Telegram alerts.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def root():
    return {"app": "WebTestingTrading", "docs": "/docs"}
