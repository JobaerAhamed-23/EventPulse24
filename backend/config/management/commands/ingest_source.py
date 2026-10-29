"""Ingest one source now: inline with --sync, otherwise as a worker job (AD-11)."""

from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from apps.ingestion.services.ingest_source import ingest_source
from config.celery import app as celery_app
from domain.errors import DomainError

INGEST_TASK = "worker.tasks.ingest_source"


class Command(BaseCommand):
    help = "Ingest one source now. --sync runs it here; otherwise a worker job is enqueued."

    def add_arguments(self, parser):
        parser.add_argument("source_id", type=UUID)
        parser.add_argument("--sync", action="store_true", help="Run inline and print the result.")

    def handle(self, *args, **options):
        source_id = options["source_id"]
        if not options["sync"]:
            # config may not import worker: the job is sent by name, like beat sends the tick.
            celery_app.send_task(INGEST_TASK, args=[str(source_id)])
            self.stdout.write(f"Enqueued {INGEST_TASK} for {source_id}.")
            return
        try:
            report = ingest_source(source_id)
        except DomainError as exc:
            raise CommandError(f"{exc.code}: {exc.message}") from None
        counts = ", ".join(f"{key}={n}" for key, n in report.counts.items()) or "no items"
        error = f" [{report.error_code}]" if report.error_code else ""
        self.stdout.write(f"{report.outcome}{error}: {counts}")
