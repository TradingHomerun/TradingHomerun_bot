"""
Telegram Notifier
==================
Sendet Signal-Alerts per Telegram.

Setup:
    1. @BotFather auf Telegram → /newbot → TOKEN kopieren
    2. Bot in einen Chat schreiben, dann:
       https://api.telegram.org/bot<TOKEN>/getUpdates
       → CHAT_ID aus der Antwort kopieren
    3. In .env eintragen:
       TELEGRAM_TOKEN=dein_token
       TELEGRAM_CHAT_ID=deine_chat_id
       TELEGRAM_ENABLED=true
"""

import os
import logging
import httpx

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED  = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"


async def send_telegram_alert(signal: dict):
    if not TELEGRAM_ENABLED or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info("Telegram deaktiviert — kein Alert gesendet")
        return

    emoji = {"KAUFEN": "🟢", "VERKAUFEN": "🔴", "NEUTRAL": "🟡"}.get(signal["signal"], "⚪")
    bar   = _confidence_bar(signal["confidence"])

    msg = f"""
{emoji} *SIGNAL — {signal['symbol']}* ({signal['timeframe']})

*{signal['signal']}*
Konfidenz: {bar} `{signal['confidence']}%`
Score: `{signal['score']}/{signal['max_score']}` Indikatoren

💰 Preis: `{signal['price']}`

*Ausgelöste Signale:*
{chr(10).join(f'  • {s}' for s in signal['active_signals']) or '  —'}

🕐 `{signal['timestamp']}`
⚠️ _Kein Finanzrat — nur zu Bildungszwecken_
    """.strip()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id":    TELEGRAM_CHAT_ID,
                    "text":       msg,
                    "parse_mode": "Markdown"
                },
                timeout=10
            )
            if resp.status_code == 200:
                logger.info(f"Telegram Alert gesendet: {signal['symbol']}")
            else:
                logger.error(f"Telegram Fehler {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Telegram Exception: {e}")


def _confidence_bar(confidence: int) -> str:
    """Visuelle Konfidenz-Leiste für Telegram."""
    filled = round(confidence / 10)
    return "█" * filled + "░" * (10 - filled)

