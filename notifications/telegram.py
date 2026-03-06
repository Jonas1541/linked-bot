import os
import httpx
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def send_telegram(message: str):
    """Sends a message via Telegram Bot API. Fails silently if not configured."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{_API_URL}/sendMessage", json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
            })
    except Exception as e:
        print(f"[Telegram] Failed to send notification: {e}")


async def notify_run_summary(keyword: str, pages_scanned: int, applied: int, failed: int, skipped: int, total_today: int):
    """Sends a formatted run summary to Telegram."""
    if applied == 0 and failed > 3:
        status = "⚠️ *ATENÇÃO* — Possível bloqueio!"
    elif applied > 0:
        status = "✅ Tudo certo"
    else:
        status = "ℹ️ Nenhuma vaga nova"

    msg = (
        f"🤖 *LinkedIn Bot — Relatório*\n\n"
        f"{status}\n\n"
        f"🔍 Keyword: `{keyword}`\n"
        f"📄 Páginas: {pages_scanned}\n"
        f"✅ Aplicadas: {applied}\n"
        f"❌ Falharam: {failed}\n"
        f"⏭️ Puladas: {skipped}\n"
        f"📊 Total hoje: {total_today}"
    )
    
    await send_telegram(msg)


async def notify_error(error: str):
    """Sends an error alert to Telegram."""
    msg = f"🚨 *LinkedIn Bot — ERRO*\n\n`{error[:500]}`"
    await send_telegram(msg)
