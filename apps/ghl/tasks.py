import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='apps.ghl.tasks.refresh_ghl_tokens', bind=True, max_retries=3)
def refresh_ghl_tokens(self):
    """Proactively refresh the GHL company and location tokens every 30 minutes.

    Scheduled via CELERY_BEAT_SCHEDULE in settings. Using Celery Beat ensures
    tokens stay fresh even when no user traffic is hitting the app.
    """
    try:
        from .oauth import refresh_company_token
        refresh_company_token()
        logger.info('GHL tokens refreshed successfully.')
        return {'ok': True}
    except Exception as exc:
        logger.error('GHL token refresh failed: %s', exc)
        raise self.retry(exc=exc, countdown=60)
