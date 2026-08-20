"""
Management command: delete_imported_jobs

Deletes every Job with is_imported=True — i.e. everything created by
import_activities_csv. JobProduct and JobStaff rows for those jobs are
removed automatically via cascade.

This is the rollback for import_activities_csv: run it if you want to wipe
the backfilled set and start over (import_activities_csv itself already does
this same delete before each run, so you normally don't need to call this
separately — it's here for when you want the data gone without re-importing).

Usage:
    python manage.py delete_imported_jobs             # asks for confirmation
    python manage.py delete_imported_jobs --yes        # skip confirmation
    python manage.py delete_imported_jobs --dry-run    # just show the count
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.jobs.models import Job


class Command(BaseCommand):
    help = 'Delete every Job with is_imported=True (and its JobProduct/JobStaff rows).'

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true',
                            help='Skip the confirmation prompt.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Only show how many jobs would be deleted.')

    def handle(self, *args, **options):
        count = Job.objects.filter(is_imported=True).count()
        if count == 0:
            self.stdout.write('No imported jobs found (is_imported=True) — nothing to delete.')
            return

        self.stdout.write(f'Found {count} imported jobs (is_imported=True).')

        if options['dry_run']:
            self.stdout.write(self.style.WARNING(f'[dry-run] would delete {count} jobs.'))
            return

        if not options['yes']:
            answer = input(f'Delete {count} imported jobs and their product/staff links? [y/N] ')
            if answer.strip().lower() != 'y':
                self.stdout.write('Aborted.')
                return

        with transaction.atomic():
            deleted_total, deleted_by_model = Job.objects.filter(is_imported=True).delete()

        self.stdout.write(self.style.SUCCESS(
            f'Deleted {deleted_by_model.get("jobs.Job", 0)} jobs '
            f'({deleted_total} rows total across related tables).'
        ))
