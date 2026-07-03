"""
Real SMS delivery via Twilio -- the outbound side of the closed loop.

Gated entirely on env vars: if Twilio creds are absent, send_sms() is a no-op
that reports `sent: False`, and the app falls back to the in-app phone panel.
So the demo works with or without a Twilio account.

Env (set with `edgeone makers env set` so they reach the deployed runtime):
  TWILIO_ACCOUNT_SID   -- from the Twilio console
  TWILIO_AUTH_TOKEN    -- from the Twilio console
  TWILIO_FROM_NUMBER   -- your Twilio number, E.164 e.g. +14155550100
  DEMO_PAGER_NUMBER    -- optional: force ALL pages to this one phone for the
                          demo (E.164), overriding the case's listed number.
                          Twilio trial accounts can only text VERIFIED numbers,
                          so set this to your verified demo phone.
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def sms_configured() -> bool:
    return bool(
        os.getenv("TWILIO_ACCOUNT_SID")
        and os.getenv("TWILIO_AUTH_TOKEN")
        and os.getenv("TWILIO_FROM_NUMBER")
    )


def target_number(case_number: str) -> str:
    """Where the page actually goes -- demo override wins so judges get the text."""
    return os.getenv("DEMO_PAGER_NUMBER", "").strip() or case_number


def send_sms(to: str, body: str) -> dict:
    """Send one SMS. Returns {sent: bool, sid?: str, error?: str}."""
    if not sms_configured():
        return {"sent": False, "reason": "twilio_not_configured"}

    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_FROM_NUMBER", "")
    to = target_number(to)

    try:
        import httpx
        resp = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            auth=(sid, token),
            data={"From": from_number, "To": to, "Body": body[:1500]},
            timeout=20.0,
        )
        if resp.status_code >= 400:
            return {"sent": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        return {"sent": True, "sid": resp.json().get("sid"), "to": to}
    except Exception as e:  # noqa: BLE001
        return {"sent": False, "error": f"{type(e).__name__}: {e}"}
