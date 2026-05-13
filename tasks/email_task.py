"""Celery task: send personalised presentation email to a lead."""
from __future__ import annotations

import logging

from tasks.celery_app import app

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(self, lead_id: str) -> dict:
    """Fetch the lead from Supabase, generate an email with Claude, and send via SendGrid.

    This task is enqueued by the webhook handler when the reception signals that
    they want to receive more information by email.

    Args:
        lead_id: UUID of the lead that requested the email.

    Returns:
        Dict with ``status`` key: ``"sent"``, ``"no_email"``, or ``"failed"``.
    """
    from agents.email_writer import EmailWriter  # noqa: PLC0415 (lazy import avoids circular dep)
    from db.client import get_client  # noqa: PLC0415

    db = get_client()
    writer = EmailWriter()

    try:
        result = db.table("leads").select("*").eq("id", lead_id).maybe_single().execute()
        if not result.data:
            logger.warning("Email task: lead %s not found", lead_id)
            return {"status": "lead_not_found"}

        lead = result.data

        if not writer.can_send(lead):
            # No corporate email yet — mark lead for collection
            logger.info("Lead %s has no email; marking as email_requested", lead_id)
            db.table("leads").update({"status": "email_requested"}).eq("id", lead_id).execute()
            return {"status": "no_email"}

        success = writer.send(lead)
        return {"status": "sent" if success else "failed"}

    except Exception as exc:
        logger.exception("Email task failed for lead %s", lead_id)
        raise self.retry(exc=exc)
