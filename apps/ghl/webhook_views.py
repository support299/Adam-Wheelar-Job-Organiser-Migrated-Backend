"""Public webhook endpoint — no authentication required.

Receives Contact and User events from GoHighLevel and upserts them into the
local database. Mirrors the behaviour of ghl-webhook.ts in the original project.
"""

import logging

import requests
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contacts.models import GhlContact, GhlUser

from .models import GhlWebhookLog
from .oauth import get_valid_location_token

logger = logging.getLogger(__name__)


def _log(status, **kwargs):
    try:
        GhlWebhookLog.objects.create(status=status, **kwargs)
    except Exception as exc:
        logger.error('Failed to write webhook log: %s', exc)


def _build_name(payload: dict) -> str | None:
    parts = [payload.get('firstName'), payload.get('lastName')]
    name = ' '.join(p for p in parts if p).strip()
    return name or payload.get('name') or None


def _fetch_assigned_user_id(contact_id: str, location_id: str | None) -> str | None:
    try:
        token, _ = get_valid_location_token()
    except Exception:
        return None
    try:
        resp = requests.get(
            f'https://services.leadconnectorhq.com/contacts/{contact_id}',
            headers={
                'Accept': 'application/json',
                'Version': '2021-07-28',
                'Authorization': f'Bearer {token}',
            },
            timeout=10,
        )
        if not resp.ok:
            return None
        return resp.json().get('contact', {}).get('assignedTo')
    except Exception as exc:
        logger.error('GHL contact fetch error: %s', exc)
        return None


def _handle_event(payload: dict) -> dict:
    event_type: str = payload.get('type', '')
    entity_id: str | None = payload.get('id')

    if not entity_id:
        _log('skipped', type=event_type, error='missing id', payload=payload)
        return {'skipped': True, 'reason': 'missing id'}

    is_contact = event_type.startswith('Contact')
    is_user = event_type.startswith('User')

    if not is_contact and not is_user:
        _log(
            'skipped',
            type=event_type,
            entity_id=entity_id,
            error=f'unsupported type {event_type}',
            payload=payload,
        )
        return {'skipped': True, 'reason': f'unsupported type {event_type}'}

    table = 'ghl_contacts' if is_contact else 'ghl_users'

    if event_type.endswith('Delete'):
        _log(
            'skipped',
            type=event_type,
            entity_id=entity_id,
            entity_table=table,
            action='delete-ignored',
            payload=payload,
        )
        return {'ok': True, 'action': 'delete-ignored', 'table': table, 'id': entity_id}

    try:
        row_data = {
            'name': _build_name(payload),
            'email': payload.get('email'),
            'phone': payload.get('phone'),
            'type': event_type,
            'location_id': payload.get('locationId'),
            'raw': payload,
        }

        if is_contact:
            if assigned := _fetch_assigned_user_id(entity_id, payload.get('locationId')):
                row_data['user_id'] = assigned
            GhlContact.objects.update_or_create(id=entity_id, defaults=row_data)
        else:
            GhlUser.objects.update_or_create(id=entity_id, defaults=row_data)

        _log(
            'success',
            type=event_type,
            entity_id=entity_id,
            entity_table=table,
            action='upserted',
            payload=payload,
        )
        return {'ok': True, 'action': 'upserted', 'table': table, 'id': entity_id}

    except Exception as exc:
        _log(
            'error',
            type=event_type,
            entity_id=entity_id,
            entity_table=table,
            error=str(exc),
            payload=payload,
        )
        raise


@method_decorator(csrf_exempt, name='dispatch')
class GhlWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        body = request.data
        events = body if isinstance(body, list) else [body]
        results = []
        for evt in events:
            payload = evt.get('body', evt) if isinstance(evt, dict) else evt
            try:
                results.append(_handle_event(payload))
            except Exception as exc:
                logger.error('Webhook event error: %s', exc)
                results.append({'ok': False, 'error': str(exc)})
        return Response({'success': True, 'results': results})
