"""
Management command: import_activities_csv

Imports the historic CRM "activities" export (csv/crm_activities_export_*.csv)
into the Job table as completed, historic job records.

Each CSV row is one logged CRM activity (a call, a scheduled visit, a workflow
trigger, ...). A row becomes a Job when it has a real "Raw Due Datetime" (not
blank / not the "00000000000000" placeholder) AND its Contact ID can be
matched to exactly one existing GhlContact:

  1. exact match on the legacy contact ID stored in GhlContact.raw's
     "cdhOVLorSBgO3VwWwamM" custom field (this is the same ID space as the
     CSV's "Contact ID" column)
  2. fallback: phone (Contact Phone, then Contact Mobile)
  3. fallback: email
  4. fallback: first name

Every job produced by this command is marked Status = Completed (this is
historic data — everything already happened). service_date/service_time come
from the row's due datetime; completed_at comes from its completed datetime
when present.

Address comes from the matched contact's GHL record. Amount / Products (line
items) are the union of every distinct product across ALL of that contact's
existing jobs (deduped by product, Amount = their total) — this CSV itself
carries none of those fields, so every new job for a contact gets that same
full product set. Assigned Staff is matched by name against the Staff table;
unmatched names are left unassigned (not auto-created).

Re-running this command replaces the whole is_imported=True set (it does not
upsert row-by-row) so it's always safe to run again after fixing the source
CSV or the Staff/GhlContact tables.

Rows that can't be turned into a clean Job are not silently dropped — they're
written to review CSVs instead, under media/activities_import_review/<run
timestamp>/ (each run gets its own folder so nothing gets overwritten):
  * skipped_no_due_date.csv      - no real "Raw Due Datetime", so no Job was
                                    even attempted
  * contacts_not_found.csv       - Contact ID/phone/email/first name matched no GhlContact
  * contacts_ambiguous.csv       - matched more than one GhlContact
  * missing_completed_date.csv   - job created, but had no real completed datetime
  * no_previous_job_products.csv - job created, but the contact had no prior
                                    Job to copy Amount / Products from

Usage:
    python manage.py import_activities_csv
    python manage.py import_activities_csv --file "/path/to/file.csv"
    python manage.py import_activities_csv --limit 200      # only first 200 rows
    python manage.py import_activities_csv --dry-run
"""

import csv
import glob
import os
import re
from collections import defaultdict
from datetime import datetime, time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.contacts.models import GhlContact
from apps.jobs.models import Job, JobProduct, JobStaff, JobStatus
from apps.staff.models import Staff

# Custom field on GhlContact.raw that carries the legacy CRM contact ID —
# the same ID space as this CSV's "Contact ID" column.
LEGACY_CONTACT_ID_FIELD = 'cdhOVLorSBgO3VwWwamM'
DEFAULT_SERVICE_TIME = time(9, 0)

REVIEW_FILES = {
    'no_due_date': 'skipped_no_due_date.csv',
    'not_found': 'contacts_not_found.csv',
    'ambiguous': 'contacts_ambiguous.csv',
    'no_completed_date': 'missing_completed_date.csv',
    'no_previous_products': 'no_previous_job_products.csv',
}


def _backend_dir() -> str:
    # backend/apps/jobs/management/commands/ -> backend/
    return os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')
    )


def _default_csv_path() -> str | None:
    matches = sorted(glob.glob(os.path.join(_backend_dir(), 'csv', 'crm_activities_export_*.csv')))
    return matches[-1] if matches else None


def _default_review_dir() -> str:
    # Each run gets its own timestamped subfolder so review CSVs from
    # different runs never overwrite each other.
    stamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join(_backend_dir(), 'media', 'activities_import_review', stamp)


def _clean(value) -> str:
    return (value or '').strip()


def _digits(value) -> str:
    return re.sub(r'\D', '', value or '')


def _first_name(name: str) -> str:
    name = _clean(name)
    return name.split()[0].lower() if name else ''


def _parse_raw_datetime(raw) -> datetime | None:
    """Parse a 'YYYYMMDDHHMMSS' cell; treat blank/all-zero as absent."""
    raw = _clean(raw)
    if not raw or set(raw) == {'0'}:
        return None
    try:
        return datetime.strptime(raw, '%Y%m%d%H%M%S')
    except ValueError:
        return None


class Command(BaseCommand):
    help = 'Import the historic CRM activities export CSV into the Job table (replaces is_imported=True set).'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=None, help='Path to the CSV file.')
        parser.add_argument('--limit', type=int, default=None,
                            help='Only process the first N rows (for testing).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Parse and match but do not write to the database.')
        parser.add_argument('--out-dir', default=None,
                            help='Directory to write review CSVs into.')

    def handle(self, *args, **options):
        path = options['file'] or _default_csv_path()
        if not path or not os.path.exists(path):
            raise CommandError(f'CSV file not found: {path}')

        self.stdout.write(f'Reading: {path}')
        with open(path, encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        if options['limit'] is not None:
            rows = rows[:options['limit']]
        self.stdout.write(f'Total rows: {len(rows)}')

        self._build_contact_indexes()
        self.stdout.write(
            f'Indexed {GhlContact.objects.count()} GHL contacts '
            f'({len(self.by_legacy_id)} with a legacy contact ID)'
        )
        staff_by_name = {s.name.strip().lower(): s for s in Staff.objects.all() if s.name}
        self.stdout.write(f'Staff: {len(staff_by_name)} existing (unmatched Assigned To names are left unassigned)')

        to_create: list[Job] = []
        products_by_job: dict = {}
        staff_links: list[tuple] = []
        review: dict[str, list[dict]] = defaultdict(list)
        prev_job_cache: dict = {}

        for row in rows:
            due_dt = _parse_raw_datetime(row.get('Raw Due Datetime'))
            if due_dt is None:
                review['no_due_date'].append(row)
                continue

            contact, error = self._match_contact(row)
            if error:
                review[error].append(row)
                continue

            completed_dt = _parse_raw_datetime(row.get('Raw Completed Datetime'))
            if completed_dt is None:
                review['no_completed_date'].append(row)
            completed_at = timezone.make_aware(completed_dt or due_dt)

            if contact.id not in prev_job_cache:
                prev_job_cache[contact.id] = self._contact_products(contact)
            prev = prev_job_cache[contact.id]
            if prev is None:
                review['no_previous_products'].append({
                    **row,
                    'Matched GHL Contact ID': contact.id,
                    'Matched GHL Contact Name': contact.name or '',
                })
                amount, products = 0, []
            else:
                amount, products = prev['amount'], prev['products']

            activity = _clean(row.get('Activity'))
            service_type = 'installation' if 'install' in activity.lower() else 'servicing'

            job = Job(
                name=contact.name or _clean(row.get('Contact Name')) or 'Unknown',
                email=contact.email or _clean(row.get('Contact Email')) or '',
                phone=contact.phone or _clean(row.get('Contact Phone')) or None,
                service_value=amount,
                address=self._build_address(contact),
                lat=0.0, lng=0.0,
                service_date=due_dt.date(),
                service_time=due_dt.time() if due_dt.time() != time(0, 0) else DEFAULT_SERVICE_TIME,
                status=JobStatus.COMPLETED,
                notes=_clean(row.get('Notes')) or None,
                is_recurring=False,
                frequency=None,
                ghl_contact_id=contact.id,
                is_imported=True,
                service_type=service_type,
                completed_at=completed_at,
            )
            to_create.append(job)
            products_by_job[job.id] = products

            assigned = _clean(row.get('Assigned To'))
            staff = staff_by_name.get(assigned.lower()) if assigned else None
            if staff:
                staff_links.append((job, staff))

        self.stdout.write(
            f'Matched {len(to_create)} rows into jobs  '
            f'(skipped no-due-date: {len(review["no_due_date"])}, '
            f'not-found: {len(review["not_found"])}, '
            f'ambiguous: {len(review["ambiguous"])})'
        )

        if options['dry_run']:
            self.stdout.write(self.style.WARNING(
                f'[dry-run] would create {len(to_create)} jobs, '
                f'{sum(len(p) for p in products_by_job.values())} product links, '
                f'{len(staff_links)} staff links; '
                f'missing-completed-date: {len(review["no_completed_date"])}, '
                f'no-previous-products: {len(review["no_previous_products"])}'
            ))
            self._write_review_csvs(rows, review, options['out_dir'])
            return

        with transaction.atomic():
            deleted_counts = Job.objects.filter(is_imported=True).delete()
            deleted_jobs = deleted_counts[1].get('jobs.Job', 0)
            Job.objects.bulk_create(to_create, batch_size=500)

            jp_objs = [
                JobProduct(job_id=job.id, product_id=p['product_id'],
                           quantity=p['quantity'], unit_price=p['unit_price'])
                for job in to_create for p in products_by_job.get(job.id, [])
            ]
            JobProduct.objects.bulk_create(jp_objs, batch_size=500)

            js_objs = [JobStaff(job=job, staff=staff) for job, staff in staff_links]
            JobStaff.objects.bulk_create(js_objs, batch_size=500, ignore_conflicts=True)

        review_paths = self._write_review_csvs(rows, review, options['out_dir'])

        self.stdout.write(self.style.SUCCESS(
            f'Done. replaced {deleted_jobs} previously-imported jobs with '
            f'{len(to_create)} new ones  '
            f'(product links: {len(jp_objs)}, staff links: {len(js_objs)})'
        ))
        for key, path in review_paths.items():
            self.stdout.write(f'  {key}: {path}')

    # ── contact matching ──────────────────────────────────────────────────

    def _build_contact_indexes(self):
        self.by_legacy_id = defaultdict(list)
        self.by_phone = defaultdict(list)
        self.by_email = defaultdict(list)
        self.by_first_name = defaultdict(list)
        for c in GhlContact.objects.all():
            raw = c.raw or {}
            for cf in raw.get('customFields') or []:
                if cf.get('id') == LEGACY_CONTACT_ID_FIELD:
                    val = _clean(cf.get('value'))
                    if val:
                        self.by_legacy_id[val].append(c)
            phone_d = _digits(c.phone)
            if phone_d:
                self.by_phone[phone_d[-10:]].append(c)
            if c.email:
                self.by_email[c.email.strip().lower()].append(c)
            fn = _first_name(c.name)
            if fn:
                self.by_first_name[fn].append(c)

    def _match_contact(self, row: dict):
        """Return (contact, None) on a clean match, or (None, 'not_found'|'ambiguous')."""
        contact_id = _clean(row.get('Contact ID'))
        candidates = self.by_legacy_id.get(contact_id, []) if contact_id else []

        if not candidates:
            for phone_col in ('Contact Phone', 'Contact Mobile'):
                phone_d = _digits(row.get(phone_col))
                if phone_d:
                    candidates = self.by_phone.get(phone_d[-10:], [])
                    if candidates:
                        break

        if not candidates:
            email = _clean(row.get('Contact Email')).lower()
            if email:
                candidates = self.by_email.get(email, [])

        if not candidates:
            fn = _first_name(row.get('Contact Name'))
            if fn:
                candidates = self.by_first_name.get(fn, [])

        uniq = list({c.id: c for c in candidates}.values())
        if len(uniq) == 1:
            return uniq[0], None
        if not uniq:
            return None, 'not_found'
        return None, 'ambiguous'

    @staticmethod
    def _build_address(contact: GhlContact) -> str:
        raw = contact.raw or {}
        parts = [raw.get('address1'), raw.get('city'), raw.get('state'),
                  raw.get('postalCode'), raw.get('country')]
        return ', '.join(p.strip() for p in parts if p and p.strip())

    @staticmethod
    def _contact_products(contact: GhlContact) -> dict | None:
        """Every distinct product across all of this contact's existing jobs."""
        job_ids = list(Job.objects.filter(ghl_contact_id=contact.id).values_list('id', flat=True))
        if not job_ids:
            return None
        lines = JobProduct.objects.filter(job_id__in=job_ids).values(
            'product_id', 'quantity', 'unit_price'
        )
        by_product = {}
        for line in lines:
            # One row per product — last one seen wins if the contact has the
            # same product on more than one prior job.
            by_product[line['product_id']] = line
        if not by_product:
            return None
        products = list(by_product.values())
        amount = sum(p['quantity'] * p['unit_price'] for p in products)
        return {'amount': amount, 'products': products}

    # ── review CSVs ──────────────────────────────────────────────────────

    @staticmethod
    def _write_review_csvs(rows, review: dict, out_dir: str | None) -> dict[str, str]:
        out_dir = out_dir or _default_review_dir()
        os.makedirs(out_dir, exist_ok=True)
        base_fieldnames = list(rows[0].keys()) if rows else []
        written = {}
        for key, filename in REVIEW_FILES.items():
            data = review.get(key, [])
            if not data:
                continue
            path = os.path.join(out_dir, filename)
            fieldnames = list(dict.fromkeys(
                base_fieldnames + [k for r in data for k in r.keys() if k not in base_fieldnames]
            ))
            with open(path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)
            written[key] = path
        return written
