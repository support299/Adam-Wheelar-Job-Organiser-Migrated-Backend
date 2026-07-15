"""GoHighLevel OAuth helpers — ported directly from ghl.functions.ts."""

import logging
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone as dj_timezone

from .models import GhlToken

logger = logging.getLogger(__name__)

GHL_NAME_CUSTOM_FIELD_ID = 'pm9cdiSMgL9HHQRli7nj'


def _post_token(params: dict) -> dict:
    body = {
        'client_id': settings.GHL_CLIENT_ID,
        'client_secret': settings.GHL_CLIENT_SECRET,
        **params,
    }
    resp = requests.post(
        settings.GHL_TOKEN_URL,
        data=body,
        headers={'Accept': 'application/json'},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _mint_location_token(company_access_token: str, company_id: str, location_id: str) -> dict:
    resp = requests.post(
        settings.GHL_LOCATION_TOKEN_URL,
        json={'companyId': company_id, 'locationId': location_id},
        headers={
            'Accept': 'application/json',
            'Version': '2021-07-28',
            'Authorization': f'Bearer {company_access_token}',
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _persist_token(token_data: dict) -> GhlToken:
    expires_at = dj_timezone.now() + timedelta(seconds=token_data.get('expires_in', 3600))
    location_id = token_data.get('locationId') or None
    company_id = token_data.get('companyId') or None

    defaults = {
        'access_token': token_data['access_token'],
        'refresh_token': token_data.get('refresh_token', ''),
        'expires_at': expires_at,
        'company_id': company_id,
        'user_type': token_data.get('userType'),
        'scope': token_data.get('scope'),
        'raw': token_data,
    }

    if location_id:
        obj, _ = GhlToken.objects.update_or_create(location_id=location_id, defaults=defaults)
    else:
        # Company token: enforce single row
        obj = GhlToken.objects.filter(location_id__isnull=True).first()
        if obj:
            for k, v in defaults.items():
                setattr(obj, k, v)
            obj.location_id = None
            obj.save()
        else:
            obj = GhlToken.objects.create(location_id=None, **defaults)

    return obj


def build_authorize_url() -> str:
    """Build the GHL OAuth authorization URL for the browser redirect."""
    # version_id is the portion of the client_id before the first '-'
    version_id = settings.GHL_CLIENT_ID.split('-')[0]
    params = {
        'response_type': 'code',
        'redirect_uri': settings.GHL_REDIRECT_URI,
        'client_id': settings.GHL_CLIENT_ID,
        'scope': settings.GHL_SCOPES,
        'version_id': version_id,
    }
    return settings.GHL_AUTHORIZE_URL + '?' + urlencode(params)


def exchange_code(code: str, redirect_uri: str) -> None:
    """Exchange an authorization code for company + location tokens."""
    token = _post_token({
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'user_type': 'Location',
    })
    _persist_token(token)
    _exchange_and_store_location(token)


def refresh_company_token() -> None:
    """Refresh the company token and re-mint the location token."""
    company_row = GhlToken.objects.filter(location_id__isnull=True).first()
    if not company_row:
        raise ValueError('No GHL company connection found. Please install first.')

    token = _post_token({
        'grant_type': 'refresh_token',
        'refresh_token': company_row.refresh_token,
        'user_type': 'Company',
    })
    _persist_token(token)
    _exchange_and_store_location(token)


def _exchange_and_store_location(company_token: dict) -> None:
    location_id = settings.GHL_LOCATION_ID
    if not location_id:
        logger.warning('GHL_LOCATION_ID not configured — skipping location token mint.')
        return
    company_id = company_token.get('companyId')
    if not company_id:
        return
    loc_token = _mint_location_token(
        company_token['access_token'], company_id, location_id
    )
    if not loc_token.get('locationId'):
        loc_token['locationId'] = location_id
    if not loc_token.get('companyId'):
        loc_token['companyId'] = company_id
    if not loc_token.get('userType'):
        loc_token['userType'] = 'Location'
    _persist_token(loc_token)


def get_valid_location_token() -> tuple[str, str]:
    """Return (access_token, location_id), refreshing if the token expires within 60 s."""
    row = (
        GhlToken.objects.filter(location_id__isnull=False)
        .order_by('-updated_at')
        .first()
    )
    if not row:
        raise ValueError('No GHL location connection found.')

    if row.expires_at - dj_timezone.now() > timedelta(seconds=60):
        return row.access_token, row.location_id

    # Token is about to expire — refresh
    company_row = GhlToken.objects.filter(location_id__isnull=True).first()
    if not company_row:
        raise ValueError('No GHL company connection for refresh.')

    token = _post_token({
        'grant_type': 'refresh_token',
        'refresh_token': company_row.refresh_token,
        'user_type': 'Location',
    })
    if not token.get('locationId'):
        token['locationId'] = row.location_id
    if not token.get('companyId'):
        token['companyId'] = row.company_id
    if not token.get('userType'):
        token['userType'] = 'Location'
    obj = _persist_token(token)
    return obj.access_token, obj.location_id


def sync_location_contacts() -> int:
    """Fetch every contact for the connected location from GHL and upsert into GhlContact.

    Returns the number of contacts upserted.
    Uses cursor-based pagination (startAfterId) to handle large contact lists.
    """
    from apps.contacts.models import GhlContact  # local import avoids circular deps

    access_token, location_id = get_valid_location_token()
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Version': '2021-07-28',
        'Accept': 'application/json',
    }

    synced = 0
    start_after_id = None

    while True:
        params: dict = {'locationId': location_id, 'limit': 100}
        if start_after_id:
            params['startAfterId'] = start_after_id

        resp = requests.get(
            settings.GHL_CONTACTS_URL,
            headers=headers,
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        contacts = data.get('contacts', [])
        if not contacts:
            break

        for c in contacts:
            contact_id = c.get('id')
            if not contact_id:
                continue
            first = c.get('firstName') or ''
            last = c.get('lastName') or ''
            name = c.get('name') or (f'{first} {last}'.strip()) or None
            GhlContact.objects.update_or_create(
                id=contact_id,
                defaults={
                    'name': name,
                    'email': c.get('email') or None,
                    'phone': c.get('phone') or None,
                    'type': c.get('type') or None,
                    'location_id': c.get('locationId') or location_id,
                    'user_id': c.get('assignedTo') or None,
                    'raw': c,
                },
            )
            synced += 1

        meta = data.get('meta', {})
        next_cursor = meta.get('startAfterId')
        # Stop if no next cursor or we got a partial page
        if not next_cursor or len(contacts) < 100:
            break
        start_after_id = next_cursor

    logger.info('GHL contact sync complete: %d contacts upserted for location %s', synced, location_id)
    return synced


def update_contact_custom_field(contact_id: str, name_value: str) -> dict:
    """Set the 'name' custom field on a GHL contact via PUT /contacts/{id}."""
    access_token, _ = get_valid_location_token()
    resp = requests.put(
        f'{settings.GHL_CONTACTS_URL}/{contact_id}',
        json={
            'customFields': [
                {'id': GHL_NAME_CUSTOM_FIELD_ID, 'fieldValue': name_value},
            ],
        },
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Version': 'v3',
            'Authorization': f'Bearer {access_token}',
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_install_config() -> dict:
    return {
        'clientId': settings.GHL_CLIENT_ID,
        'scopes': settings.GHL_SCOPES,
        'locationId': settings.GHL_LOCATION_ID,
        'configured': bool(
            settings.GHL_CLIENT_ID
            and settings.GHL_CLIENT_SECRET
            and settings.GHL_LOCATION_ID
        ),
    }


def get_token_status() -> dict:
    company = (
        GhlToken.objects.filter(location_id__isnull=True)
        .values('expires_at', 'location_id', 'company_id', 'user_type', 'scope', 'updated_at')
        .first()
    )
    location = (
        GhlToken.objects.filter(location_id__isnull=False)
        .order_by('location_id')
        .values('expires_at', 'location_id', 'company_id', 'user_type', 'scope', 'updated_at')
        .first()
    )
    return {'company': company, 'location': location}
