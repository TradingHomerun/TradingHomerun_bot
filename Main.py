"""
TradingView Signal Bot — FastAPI Backend
========================================
7-Indikator Signal Engine für professionelles Trading.

Setup:
    pip install fastapi uvicorn pydantic python-dotenv httpx

Starten:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

TradingView Webhook URL:
    http://DEINE-SERVER-IP:8000/webhook
"""

import os
import logging
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from signals import evaluate_signals, SignalResult
from notifier import send_telegram_alert

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TradingView Signal Bot",
    description="7-Indikator Signal-Scoring Engine",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "mein-geheimer-key")

# In-Memory History (für Production: PostgreSQL verwenden)
signal_history: list[dict] = []


class TradingViewPayload(BaseModel):
    """
    JSON-Payload von TradingView.

    Im TradingView Alert-Message-Feld eintragen:
    {
        "secret":        "mein-geheimer-key",
        "symbol":        "{{ticker}}",
        "timeframe":     "{{interval}}",
        "close":         {{close}},
        "open":          {{open}},
        "high":          {{high}},
        "low":           {{low}},
        "volume":        {{volume}},
        "rsi":           {{plot("RSI")}},
        "macd":          {{plot("MACD")}},
        "macd_signal":   {{plot("Signal")}},
        "ema20":         {{plot("EMA20")}},
        "ema50":         {{plot("EMA50")}},
        "ema200":        {{plot("EMA200")}},
        "bb_upper":      {{plot("BB_Upper")}},
        "bb_lower":      {{plot("BB_Lower")}},
        "bb_basis":      {{plot("BB_Basis")}},
        "obv":           {{plot("OBV")}},
        "obv_ema":       {{plot("OBV_EMA")}},
        "pivot_r1":      {{plot("R1")}},
        "pivot_s1":      {{plot("S1")}},
        "fear_greed":    {{plot("FearGreed")}}
    }
    """
    secret: str
    symbol: str
    timeframe: str
    close: float
    open: float
    high: float
    low: float
    volume: float

    # 1. Trend — EMA
    ema20:        Optional[float] = None
    ema50:        Optional[float] = None
    ema200:       Optional[float] = None

    # 2. Momentum — RSI
    rsi:          Optional[float] = None

    # 3. Momentum-Bestätigung — MACD
    macd:         Optional[float] = None
    macd_signal:  Optional[float] = None

    # 4. Volatilität — Bollinger Bands
    bb_upper:     Optional[float] = None
    bb_lower:     Optional[float] = None
    bb_basis:     Optional[float] = None

    # 5. Volumen — OBV
    obv:          Optional[float] = None
    obv_ema:      Optional[float] = None

    # 6. Marktstruktur — Pivot Points
    pivot_r1:     Optional[float] = None
    pivot_s1:     Optional[float] = None

    # 7. Sentiment — Fear & Greed (0–100)
    fear_greed:   Optional[float] = None


@app.get("/")
def health():
    return {
        "status": "online",
        "version": "2.0.0",
        "indicators": 7,
        "signals_processed": len(signal_history),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/webhook")
async def receive_webhook(payload: TradingViewPayload):
    """Empfängt TradingView Webhook und bewertet alle 7 Indikatoren."""

    if payload.secret != WEBHOOK_SECRET:
        logger.warning(f"Ungültiger Key — {payload.symbol}")
        raise HTTPException(status_code=403, detail="Ungültiger Secret-Key")

    logger.info(f"Webhook: {payload.symbol} @ {payload.close} ({payload.timeframe})")

    result: SignalResult = evaluate_signals(payload)

    entry = {
        "timestamp":      datetime.utcnow().isoformat(),
        "symbol":         payload.symbol,
        "timeframe":      payload.timeframe,
        "price":          payload.close,
        "signal":         result.signal,
        "score":          result.score,
        "max_score":      result.max_score,
        "confidence":     result.confidence,
        "active_signals": result.active_signals,
        "details":        result.details
    }
    signal_history.append(entry)

    # Telegram Alert bei starkem Signal (Score ≥ 5 von 7)
    if result.score >= 5:
        await send_telegram_alert(entry)

    logger.info(
        f"→ {result.signal} | Score: {result.score}/{result.max_score} "
        f"| Konfidenz: {result.confidence}%"
    )

    return entry


@app.get("/signals")
def get_signals(limit: int = 50, symbol: Optional[str] = None):
    """Gibt die letzten Signale zurück."""
    history = signal_history
    if symbol:
        history = [s for s in history if s["symbol"].upper() == symbol.upper()]
    return {
        "total":   len(history),
        "signals": history[-limit:][::-1]
    }


@app.get("/signals/stats")
def get_stats():
    """Aggregierte Statistiken über alle Signale."""
    if not signal_history:
        return {"message": "Noch keine Signale verarbeitet"}

    counts = {"KAUFEN": 0, "VERKAUFEN": 0, "NEUTRAL": 0}
    for s in signal_history:
        counts[s["signal"]] = counts.get(s["signal"], 0) + 1

    avg_conf = sum(s["confidence"] for s in signal_history) / len(signal_history)
    symbols  = list({s["symbol"] for s in signal_history})

    return {
        "total_signals":    len(signal_history),
        "distribution":     counts,
        "avg_confidence":   round(avg_conf, 1),
        "symbols_tracked":  symbols
    }
