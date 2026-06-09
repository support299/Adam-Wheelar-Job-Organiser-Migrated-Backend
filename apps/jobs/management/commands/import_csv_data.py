"""
Management command: import_csv_data
Reads all CSV exports from backend/csv/ and upserts them into the database.

Usage:
    python manage.py import_csv_data
"""

import csv
import glob
import json
import os
from datetime import date, datetime, time

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.contacts.models import ContactNote, GhlContact, GhlUser
from apps.jobs.models import Job, JobCompletion, JobProduct, JobStaff
from apps.locations.models import BaseLocation
from apps.plans.models import JobProgress, SavedPlan
from apps.products.models import Product
from apps.staff.models import Staff


# ── helpers ──────────────────────────────────────────────────────────────────

def _csv_dir() -> str:
    return os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'csv')
    )


def _find(pattern: str) -> list[str]:
    return sorted(glob.glob(os.path.join(_csv_dir(), pattern)))


def _read(path: str) -> list[dict]:
    """Read a semicolon-delimited CSV; strip leading/trailing whitespace from all values."""
    with open(path, encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        return [{k: (v.strip() if v else '') for k, v in row.items()} for row in reader]


def _dt(s: str) -> datetime | None:
    if not s:
        return None
    # '+00' → '+00:00' for fromisoformat
    if s.endswith('+00'):
        s = s[:-3] + '+00:00'
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _date(s: str) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def _time(s: str) -> time | None:
    try:
        return time.fromisoformat(s) if s else None
    except ValueError:
        return None


def _bool(s: str) -> bool:
    return s.lower() == 'true'


def _json(s: str):
    try:
        return json.loads(s) if s else None
    except (json.JSONDecodeError, TypeError):
        return None


def _str(s: str) -> str | None:
    return s if s else None


def _float(s: str) -> float | None:
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _int(s: str, default: int = 0) -> int:
    try:
        return int(s) if s else default
    except ValueError:
        return default


# ── command ───────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Upsert all CSV exports from backend/csv/ into the database'

    def handle(self, *args, **options):
        self.stdout.write(f'Reading CSVs from: {_csv_dir()}')
        with transaction.atomic():
            self._base_locations()
            self._products()
            self._ghl_users()
            self._ghl_contacts()
            self._jobs()
            self._job_staff()
            self._job_products()
            self._job_completions()
            self._saved_plans()
            self._job_progress()
            self._contact_notes()
        self.stdout.write(self.style.SUCCESS('Done.'))

    # ── individual importers ──────────────────────────────────────────────────

    def _base_locations(self):
        seen, n = set(), 0
        for path in _find('base_locations-*.csv'):
            for r in _read(path):
                if r['id'] in seen:
                    continue
                seen.add(r['id'])
                BaseLocation.objects.update_or_create(
                    id=r['id'],
                    defaults={'name': r['name'], 'address': r['address'],
                              'lat': float(r['lat']), 'lng': float(r['lng'])},
                )
                BaseLocation.objects.filter(id=r['id']).update(
                    created_at=_dt(r['created_at']), updated_at=_dt(r['updated_at'])
                )
                n += 1
        self.stdout.write(f'  base_locations  {n}')

    def _products(self):
        n = 0
        for path in _find('products-*.csv'):
            for r in _read(path):
                Product.objects.update_or_create(
                    id=r['id'],
                    defaults={
                        'name': r['name'],
                        'sku': _str(r.get('sku', '')),
                        'price': r.get('price') or '0',
                        'description': _str(r.get('description', '')),
                        'active': _bool(r.get('active', 'true')),
                    },
                )
                Product.objects.filter(id=r['id']).update(
                    created_at=_dt(r['created_at']), updated_at=_dt(r['updated_at'])
                )
                n += 1
        self.stdout.write(f'  products        {n}')

    def _ghl_users(self):
        n = 0
        for path in _find('ghl_users-*.csv'):
            for r in _read(path):
                GhlUser.objects.update_or_create(
                    id=r['id'],
                    defaults={
                        'name': _str(r.get('name', '')),
                        'email': _str(r.get('email', '')),
                        'phone': _str(r.get('phone', '')),
                        'type': _str(r.get('type', '')),
                        'location_id': _str(r.get('location_id', '')),
                        'raw': _json(r.get('raw', '')),
                    },
                )
                GhlUser.objects.filter(id=r['id']).update(
                    created_at=_dt(r['created_at']), updated_at=_dt(r['updated_at'])
                )
                n += 1
        self.stdout.write(f'  ghl_users       {n}')

    def _ghl_contacts(self):
        n = 0
        for path in _find('ghl_contacts-*.csv'):
            for r in _read(path):
                GhlContact.objects.update_or_create(
                    id=r['id'],
                    defaults={
                        'name': _str(r.get('name', '')),
                        'email': _str(r.get('email', '')),
                        'phone': _str(r.get('phone', '')),
                        'type': _str(r.get('type', '')),
                        'location_id': _str(r.get('location_id', '')),
                        'user_id': _str(r.get('user_id', '')),
                        'raw': _json(r.get('raw', '')),
                    },
                )
                GhlContact.objects.filter(id=r['id']).update(
                    created_at=_dt(r['created_at']), updated_at=_dt(r['updated_at'])
                )
                n += 1
        self.stdout.write(f'  ghl_contacts    {n}')

    def _jobs(self):
        n = 0
        for path in _find('jobs-*.csv'):
            for r in _read(path):
                Job.objects.update_or_create(
                    id=r['id'],
                    defaults={
                        'name': r['name'],
                        'email': r['email'],
                        'phone': _str(r.get('phone', '')),
                        'service_value': r.get('service_value') or '0',
                        'address': r['address'],
                        'lat': float(r['lat']),
                        'lng': float(r['lng']),
                        'service_date': _date(r['service_date']),
                        'service_time': _time(r['service_time']),
                        'status': r.get('status') or 'pending',
                        'notes': _str(r.get('notes', '')),
                        'is_recurring': _bool(r.get('is_recurring', 'false')),
                        'frequency': _str(r.get('frequency', '')),
                        'ghl_contact_id': _str(r.get('ghl_contact_id', '')),
                        'service_type': r.get('service_type') or 'installation',
                        'sale_date': _date(r.get('sale_date', '')),
                        'call_status': r.get('call_status') or 'not_called',
                        'calls_made': _int(r.get('calls_made', '0')),
                    },
                )
                Job.objects.filter(id=r['id']).update(
                    created_at=_dt(r['created_at']), updated_at=_dt(r['updated_at'])
                )
                n += 1
        self.stdout.write(f'  jobs            {n}')

    def _job_staff(self):
        n, skipped = 0, 0
        for path in _find('job_staff-*.csv'):
            for r in _read(path):
                try:
                    job = Job.objects.get(id=r['job_id'])
                    staff = Staff.objects.get(id=r['staff_id'])
                    js, created = JobStaff.objects.get_or_create(job=job, staff=staff)
                    if created:
                        JobStaff.objects.filter(pk=js.pk).update(
                            created_at=_dt(r['created_at'])
                        )
                    n += 1
                except (Job.DoesNotExist, Staff.DoesNotExist) as e:
                    self.stderr.write(f'    skip job_staff {r}: {e}')
                    skipped += 1
        self.stdout.write(f'  job_staff       {n} (skipped {skipped})')

    def _job_products(self):
        n, skipped = 0, 0
        for path in _find('job_products-*.csv'):
            for r in _read(path):
                try:
                    job = Job.objects.get(id=r['job_id'])
                    product = Product.objects.get(id=r['product_id'])
                    jp, created = JobProduct.objects.get_or_create(
                        id=r['id'],
                        defaults={
                            'job': job, 'product': product,
                            'quantity': r.get('quantity') or '1',
                            'unit_price': r.get('unit_price') or '0',
                        },
                    )
                    if created:
                        JobProduct.objects.filter(id=r['id']).update(
                            created_at=_dt(r['created_at'])
                        )
                    n += 1
                except (Job.DoesNotExist, Product.DoesNotExist) as e:
                    self.stderr.write(f'    skip job_products {r["id"]}: {e}')
                    skipped += 1
        self.stdout.write(f'  job_products    {n} (skipped {skipped})')

    def _job_completions(self):
        n = 0
        for path in _find('job_completions-*.csv'):
            for r in _read(path):
                jc, created = JobCompletion.objects.get_or_create(
                    id=r['id'],
                    defaults={
                        'job_id': r.get('job_id') or None,
                        'service_date': _date(r['service_date']),
                        'service_time': _time(r.get('service_time', '')),
                        'service_value': r.get('service_value') or '0',
                        'name': r['name'],
                        'email': r['email'],
                        'phone': _str(r.get('phone', '')),
                        'address': r['address'],
                        'lat': _float(r.get('lat', '')),
                        'lng': _float(r.get('lng', '')),
                        'notes': _str(r.get('notes', '')),
                        'staff_ids': _json(r.get('staff_ids', '')) or [],
                        'product_lines': _json(r.get('product_lines', '')) or [],
                        'service_type': r.get('service_type') or 'installation',
                        'sale_date': _date(r.get('sale_date', '')),
                    },
                )
                JobCompletion.objects.filter(id=r['id']).update(
                    completed_at=_dt(r.get('completed_at', '')),
                    created_at=_dt(r.get('created_at', '')),
                )
                n += 1
        self.stdout.write(f'  job_completions {n}')

    def _saved_plans(self):
        n = 0
        for path in _find('saved_plans-*.csv'):
            for r in _read(path):
                SavedPlan.objects.update_or_create(
                    id=r['id'],
                    defaults={
                        'name': r['name'],
                        'plan_date': _date(r['plan_date']),
                        'base_id': r.get('base_id') or None,
                        'base_name': _str(r.get('base_name', '')),
                        'route_shape': r.get('route_shape') or 'round',
                        'optimize_metric': r.get('optimize_metric') or 'time',
                        'ordered_job_ids': _json(r.get('ordered_job_ids', '')) or [],
                        'staff_ids': _json(r.get('staff_ids', '')) or [],
                        'road_km': r.get('road_km') or None,
                        'road_minutes': _int(r['road_minutes']) if r.get('road_minutes') else None,
                        'legs': _json(r.get('legs', '')) or [],
                        'notes': _str(r.get('notes', '')),
                    },
                )
                SavedPlan.objects.filter(id=r['id']).update(
                    created_at=_dt(r['created_at']), updated_at=_dt(r['updated_at'])
                )
                n += 1
        self.stdout.write(f'  saved_plans     {n}')

    def _job_progress(self):
        n, skipped = 0, 0
        for path in _find('job_progress-*.csv'):
            for r in _read(path):
                try:
                    plan = SavedPlan.objects.get(id=r['plan_id'])
                    JobProgress.objects.update_or_create(
                        id=r['id'],
                        defaults={
                            'plan': plan,
                            'job_id': r['job_id'],
                            'staff_id': r['staff_id'],
                            'status': r.get('status') or 'pending',
                            'actual_km': r.get('actual_km') or None,
                            'notes': _str(r.get('notes', '')),
                        },
                    )
                    JobProgress.objects.filter(id=r['id']).update(
                        created_at=_dt(r['created_at']), updated_at=_dt(r['updated_at'])
                    )
                    n += 1
                except SavedPlan.DoesNotExist:
                    self.stderr.write(f'    skip job_progress {r["id"]}: plan {r["plan_id"]} not found')
                    skipped += 1
        self.stdout.write(f'  job_progress    {n} (skipped {skipped})')

    def _contact_notes(self):
        n = 0
        for path in _find('contact_notes-*.csv'):
            for r in _read(path):
                ContactNote.objects.get_or_create(
                    id=r['id'],
                    defaults={
                        'contact_key': r['contact_key'],
                        'job_id': r.get('job_id') or None,
                        'body': r['body'],
                    },
                )
                ContactNote.objects.filter(id=r['id']).update(
                    created_at=_dt(r['created_at']), updated_at=_dt(r['updated_at'])
                )
                n += 1
        self.stdout.write(f'  contact_notes   {n}')
