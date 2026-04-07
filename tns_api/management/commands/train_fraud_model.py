from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone

from tns_api import fraud


class Command(BaseCommand):
    help = "Train the fraud detection Isolation Forest model."

    def add_arguments(self, parser):
        parser.add_argument("--from-date", dest="from_date", help="ISO date/datetime to start training window")
        parser.add_argument("--to-date", dest="to_date", help="ISO date/datetime to end training window")

    def _parse(self, value):
        if not value:
            return None
        dt = parse_datetime(value)
        if dt:
            return dt
        d = parse_date(value)
        if d:
            return timezone.make_aware(timezone.datetime.combine(d, timezone.datetime.min.time()))
        return None

    def handle(self, *args, **options):
        from_dt = self._parse(options.get("from_date"))
        to_dt = self._parse(options.get("to_date"))

        try:
            snapshot = fraud.train_fraud_model(trained_from=from_dt, trained_to=to_dt)
        except ValueError as exc:
            raise CommandError(str(exc))

        self.stdout.write(
            self.style.SUCCESS(
                f"Fraud model trained. Snapshot {snapshot.id}, rows={snapshot.training_rows}"
            )
        )
