import threading
from typing import Optional
import requests
import json

# Simple thread‑safe storage for a single webhook URL
_url_lock = threading.Lock()
_webhook_url: str = ""

def set_webhook(url: str) -> None:
    """Register (or overwrite) the webhook endpoint that will receive JSON POSTs.
    Empty string clears the registration.
    """
    global _webhook_url
    with _url_lock:
        _webhook_url = url.strip()

def get_webhook() -> str:
    with _url_lock:
        return _webhook_url

def notify(event_type: str, payload: dict) -> None:
    """Send a notification to the registered webhook.
    The payload is wrapped in a small envelope that includes the event type and a
    timestamp. Any network errors are logged but do not raise exceptions – the
    safety workflow must continue regardless of webhook health.
    """
    url = get_webhook()
    if not url:
        return
    envelope = {
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "payload": payload,
    }
    try:
        requests.post(url, json=envelope, timeout=3)
    except Exception as e:
        print(f"[Webhook] Failed to POST to {url}: {e}")
