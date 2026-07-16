"""Notification adapter. It is inert until Telegram environment variables are configured."""

import logging
import os
from urllib.parse import urlencode
from urllib.request import urlopen

logger = logging.getLogger(__name__)


def send_status_notification(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.info("Notification suppressed: Telegram is not configured")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage?{urlencode({'chat_id': chat_id, 'text': message})}"
    try:
        with urlopen(url, timeout=5) as response:  # nosec B310: URL is built only from configuration
            return 200 <= response.status < 300
    except Exception:
        logger.exception("Telegram notification failed")
        return False
