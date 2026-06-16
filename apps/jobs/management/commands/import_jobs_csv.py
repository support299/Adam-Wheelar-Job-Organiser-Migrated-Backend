"""
Management command: import_jobs_csv

Imports the customer list ("Customer List Final - jobs importing format.csv")
into the Job table. Each row is keyed on the CSV "ContactID" column, which is
stored on Job.import_contact_id so re-running the command updates existing jobs
instead of creating duplicates.

For every row the command:
  * combines Address1/Address2/City/State/Zip/Country into a single address
  * geocodes that address via the Google Maps Routes API (server key from .env)
    and stores lat/lng — addresses are geocoded in parallel (rate-limited) and
    unchanged addresses are skipped on re-runs
  * maps the "Systems in home (User2)" codes to Product rows (creating any that
    are missing) and syncs the job's JobProduct links
  * sets notes, service_date (from "Service Due Date (User1)"), 9:00 AM time,
    pending status, recurring = yearly/annually

Groups and Tags columns are ignored. All database writes are done in bulk.

Usage:
    python manage.py import_jobs_csv
    python manage.py import_jobs_csv --file "/path/to/file.csv"
    python manage.py import_jobs_csv --limit 20          # only first 20 rows
    python manage.py import_jobs_csv --regeocode         # force re-geocoding
    python manage.py import_jobs_csv --workers 10 --qps 15
"""

import csv
import logging
import os
import threading
import time as _time_module
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.jobs.models import Job, JobProduct, JobStatus, RecurrenceFrequency
from apps.products.models import Product

GEOCODE_URL = 'https://maps.googleapis.com/maps/api/geocode/json'
ROUTES_URL = 'https://routes.googleapis.com/directions/v2:computeRoutes'
# Arbitrary reachable anchor (Halifax, NS) used to geocode an address through the
# Routes API — only the *origin's* resolved coordinate is read from the response.
GEOCODE_ANCHOR = {'location': {'latLng': {'latitude': 44.6488, 'longitude': -63.5752}}}
DEFAULT_SERVICE_TIME = time(9, 0)

JOB_UPDATE_FIELDS = [
    'name', 'email', 'phone', 'address', 'lat', 'lng', 'service_date',
    'service_time', 'status', 'notes', 'is_recurring', 'frequency',
    'ghl_contact_id', 'updated_at',
]


def _default_csv_path() -> str:
    # backend/apps/jobs/management/commands/ -> backend/
    backend_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')
    )
    return os.path.join(backend_dir, 'Customer List Final - jobs importing format.csv')


def _clean(value) -> str:
    return (value or '').strip()


def _build_address(row: dict) -> str:
    parts = [
        _clean(row.get('Address1')),
        _clean(row.get('Address2')),
        _clean(row.get('City')),
        _clean(row.get('State')),
        _clean(row.get('Zip')),
        _clean(row.get('Country')),
    ]
    return ', '.join(p for p in parts if p)


def _parse_service_date(raw: str) -> date | None:
    raw = _clean(raw)
    if not raw:
        return None
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y', '%d/%m/%Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_products(raw: str) -> list[str]:
    """Split the 'Systems in home (User2)' cell into clean product codes."""
    raw = _clean(raw)
    if not raw:
        return []
    seen, out = set(), []
    for token in raw.replace(';', ',').split(','):
        code = token.strip()
        if not code:
            continue
        key = code.lower()
        if key not in seen:
            seen.add(key)
            out.append(code)
    return out


class _RateLimiter:
    """Thread-safe limiter that spaces request starts to stay under N/second."""

    def __init__(self, max_per_second: float):
        self._interval = 1.0 / max_per_second if max_per_second > 0 else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self):
        if self._interval <= 0:
            return
        with self._lock:
            now = _time_module.monotonic()
            sleep_for = self._next - now
            if sleep_for > 0:
                _time_module.sleep(sleep_for)
                now = _time_module.monotonic()
            self._next = max(now, self._next) + self._interval


class Command(BaseCommand):
    help = 'Import / upsert the customer list CSV into the Job table (parallel geocoding + bulk writes).'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=None, help='Path to the CSV file.')
        parser.add_argument('--limit', type=int, default=None,
                            help='Only process the first N rows (for testing).')
        parser.add_argument('--regeocode', action='store_true',
                            help='Re-geocode every address even if lat/lng already set.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Parse and geocode but do not write to the database.')
        parser.add_argument('--workers', type=int, default=10,
                            help='Parallel geocoding threads (default 10).')
        parser.add_argument('--qps', type=float, default=15.0,
                            help='Max geocoding requests per second (default 15).')

    def handle(self, *args, **options):
        # Keep the terminal clean: silence per-query SQL logging so only the
        # progress/count lines below are shown.
        logging.getLogger('django.db.backends').setLevel(logging.WARNING)

        path = options['file'] or _default_csv_path()
        if not os.path.exists(path):
            raise CommandError(f'CSV file not found: {path}')

        self.api_key = settings.GOOGLE_MAPS_SERVER_API_KEY
        if not self.api_key:
            self.stderr.write(self.style.WARNING(
                'GOOGLE_MAPS_SERVER_API_KEY is not set — addresses will not be geocoded.'
            ))

        self._thread_local = threading.local()
        self._limiter = _RateLimiter(options['qps'])

        limit = options['limit']
        regeocode = options['regeocode']
        dry_run = options['dry_run']

        # ── Phase 1: read + parse ────────────────────────────────────────────
        self.stdout.write(f'Reading: {path}')
        with open(path, encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        if limit is not None:
            rows = rows[:limit]

        records, skipped, dup = [], 0, 0
        seen_ids = set()
        for idx, row in enumerate(rows):
            contact_id = _clean(row.get('ContactID'))
            if not contact_id:
                skipped += 1
                continue
            if contact_id in seen_ids:
                dup += 1  # later duplicate wins; drop the earlier parse
                records = [r for r in records if r['contact_id'] != contact_id]
            seen_ids.add(contact_id)
            records.append({
                'contact_id': contact_id,
                'name': ' '.join(p for p in [
                    _clean(row.get('Firstname')), _clean(row.get('Lastname'))
                ] if p) or 'Unknown',
                'email': _clean(row.get('Email')),
                'phone': _clean(row.get('Phone')) or None,
                'address': _build_address(row),
                'service_date': _parse_service_date(row.get('Service Due Date (User1)')) or date.today(),
                'notes': _clean(row.get('Notes')) or None,
                'ghl_contact_id': _clean(row.get('GHL Contact Id')) or None,
                'product_codes': _parse_products(row.get('Systems in home (User2)')),
            })

        self.stdout.write(
            f'Parsed {len(records)} rows  (skipped no-ContactID: {skipped}, '
            f'duplicate ContactIDs collapsed: {dup})'
        )

        # ── Phase 2: load existing jobs, decide what needs geocoding ─────────
        existing_jobs = {
            j.import_contact_id: j
            for j in Job.objects.exclude(import_contact_id__isnull=True)
        }
        self.stdout.write(f'Existing jobs in DB: {len(existing_jobs)}')

        addrs_to_geocode = set()
        for rec in records:
            ej = existing_jobs.get(rec['contact_id'])
            needs = (
                regeocode or ej is None or ej.address != rec['address']
                or not ej.lat or not ej.lng
            )
            if needs and rec['address']:
                addrs_to_geocode.add(rec['address'])

        reused = len(records) - len(addrs_to_geocode)
        self.stdout.write(
            f'Addresses to geocode: {len(addrs_to_geocode)}  '
            f'(reusing existing coords for ~{reused})'
        )

        # ── Phase 3: parallel, rate-limited geocoding ────────────────────────
        coords_map = self._geocode_many(
            sorted(addrs_to_geocode), options['workers']
        ) if (addrs_to_geocode and self.api_key) else {}

        # ── Phase 4: assemble records + resolve coordinates ──────────────────
        geocode_fail = 0
        to_create, to_update = [], []
        now = timezone.now()
        for rec in records:
            ej = existing_jobs.get(rec['contact_id'])
            lat, lng = self._resolve_coords(rec, ej, coords_map)
            if lat is None:
                geocode_fail += 1
                lat, lng = 0.0, 0.0

            values = {
                'name': rec['name'], 'email': rec['email'], 'phone': rec['phone'],
                'address': rec['address'], 'lat': lat, 'lng': lng,
                'service_date': rec['service_date'], 'service_time': DEFAULT_SERVICE_TIME,
                'status': JobStatus.PENDING, 'notes': rec['notes'],
                'is_recurring': True, 'frequency': RecurrenceFrequency.ANNUALLY,
                'ghl_contact_id': rec['ghl_contact_id'],
            }
            if ej is None:
                job = Job(import_contact_id=rec['contact_id'], **values)
                to_create.append(job)
            else:
                for k, v in values.items():
                    setattr(ej, k, v)
                ej.updated_at = now
                to_update.append(ej)

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'[dry-run] would create={len(to_create)} update={len(to_update)} '
                f'skipped={skipped} geocode_failures={geocode_fail}'
            ))
            return

        # ── Phase 5: bulk database writes ────────────────────────────────────
        with transaction.atomic():
            new_products = self._ensure_products(records)
            Job.objects.bulk_create(to_create, batch_size=500)
            Job.objects.bulk_update(to_update, fields=JOB_UPDATE_FIELDS, batch_size=500)
            self.stdout.write(
                f'Jobs written: created={len(to_create)} updated={len(to_update)}'
            )
            added, removed = self._sync_all_products(records)

        self.stdout.write(self.style.SUCCESS(
            f'Done. created={len(to_create)} updated={len(to_update)} '
            f'skipped={skipped} geocode_failures={geocode_fail} '
            f'new_products={new_products} product_links(+{added}/-{removed})'
        ))

    # ── geocoding ────────────────────────────────────────────────────────────

    def _geocode_many(self, addresses: list[str], workers: int) -> dict[str, tuple]:
        total = len(addresses)
        self.stdout.write(f'Geocoding {total} addresses with {workers} workers...')
        results: dict[str, tuple] = {}
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._geocode_one, a): a for a in addresses}
            for fut in as_completed(futures):
                addr = futures[fut]
                try:
                    coords = fut.result()
                except Exception:  # noqa: BLE001 - never let one address kill the run
                    coords = None
                if coords:
                    results[addr] = coords
                done += 1
                if done % 200 == 0 or done == total:
                    self.stdout.write(f'  geocoded {done}/{total}  (resolved {len(results)})')
        return results

    def _session(self) -> requests.Session:
        s = getattr(self._thread_local, 'session', None)
        if s is None:
            s = requests.Session()
            self._thread_local.session = s
        return s

    def _geocode_one(self, address: str) -> tuple[float, float] | None:
        if not address or not self.api_key:
            return None
        result = self._geocode_via_routes(address)
        if result is None:
            result = self._geocode_via_geocoding_api(address)
        return result

    def _geocode_via_routes(self, address: str) -> tuple[float, float] | None:
        body = {
            'origin': {'address': address},
            'destination': GEOCODE_ANCHOR,
            'travelMode': 'DRIVE',
        }
        headers = {
            'X-Goog-Api-Key': self.api_key,
            'X-Goog-FieldMask': 'routes.legs.startLocation',
        }
        for attempt in range(4):
            self._limiter.wait()
            try:
                resp = self._session().post(ROUTES_URL, json=body, headers=headers, timeout=20)
                # Back off on rate-limit / transient server errors.
                if resp.status_code in (429, 500, 503):
                    _time_module.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                routes = resp.json().get('routes') or []
                if not routes:
                    return None
                legs = routes[0].get('legs') or []
                if not legs:
                    return None
                latlng = legs[0].get('startLocation', {}).get('latLng')
                if latlng and 'latitude' in latlng and 'longitude' in latlng:
                    return (latlng['latitude'], latlng['longitude'])
                return None
            except requests.RequestException:
                _time_module.sleep(2 ** attempt)
        return None

    def _geocode_via_geocoding_api(self, address: str) -> tuple[float, float] | None:
        try:
            self._limiter.wait()
            resp = self._session().get(
                GEOCODE_URL, params={'address': address, 'key': self.api_key}, timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get('status') == 'OK' and data.get('results'):
                loc = data['results'][0]['geometry']['location']
                return (loc['lat'], loc['lng'])
        except requests.RequestException:
            pass
        return None

    @staticmethod
    def _resolve_coords(rec, ej, coords_map) -> tuple:
        """Pick coordinates: fresh geocode → existing job coords → (None) fail."""
        coords = coords_map.get(rec['address'])
        if coords:
            return coords
        if ej is not None and ej.lat and ej.lng:
            return (ej.lat, ej.lng)
        return (None, None)

    # ── products ───────────────────────────────────────────────────────────

    def _ensure_products(self, records) -> int:
        """Create any product codes that don't exist yet; build name→Product map."""
        wanted: dict[str, str] = {}
        for rec in records:
            for code in rec['product_codes']:
                wanted.setdefault(code.lower(), code)

        self._product_by_name = {
            p.name.lower(): p for p in Product.objects.all()
        }
        missing = [code for low, code in wanted.items() if low not in self._product_by_name]
        new = [Product(name=code) for code in missing]
        if new:
            Product.objects.bulk_create(new, batch_size=500)
            for p in new:
                self._product_by_name[p.name.lower()] = p
        return len(new)

    def _sync_all_products(self, records) -> tuple[int, int]:
        """Make every job's JobProduct links match its CSV codes — in bulk."""
        # contact_id -> job.id  (created jobs have python-side UUIDs already)
        job_id_by_contact = {
            j.import_contact_id: j.id
            for j in Job.objects.exclude(import_contact_id__isnull=True)
        }

        desired: dict[object, set] = {}
        for rec in records:
            job_id = job_id_by_contact.get(rec['contact_id'])
            if job_id is None:
                continue
            desired[job_id] = {
                self._product_by_name[c.lower()].id for c in rec['product_codes']
            }

        existing_links = defaultdict(set)
        link_obj_id = {}
        for jp in JobProduct.objects.filter(job_id__in=list(desired.keys())).values_list(
            'id', 'job_id', 'product_id'
        ):
            jp_id, job_id, product_id = jp
            existing_links[job_id].add(product_id)
            link_obj_id[(job_id, product_id)] = jp_id

        to_add, to_delete = [], []
        for job_id, want in desired.items():
            have = existing_links.get(job_id, set())
            for pid in want - have:
                to_add.append(JobProduct(job_id=job_id, product_id=pid))
            for pid in have - want:
                to_delete.append(link_obj_id[(job_id, pid)])

        if to_add:
            JobProduct.objects.bulk_create(to_add, batch_size=500)
        if to_delete:
            JobProduct.objects.filter(id__in=to_delete).delete()
        return len(to_add), len(to_delete)
