"""
Retroactively push all finally-approved AMS requests to CMS's uploads table.

Usage:
    docker exec ams-web python manage.py sync_approvals_to_cms
    docker exec ams-web python manage.py sync_approvals_to_cms --dry-run
"""
from django.core.management.base import BaseCommand

FINAL_STATES = ("approved", "active", "active_pending_renewal", "terminated")


class Command(BaseCommand):
    help = "Sync approved AMS requests to CMS uploads table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print which requests would be synced without actually syncing.",
        )

    def handle(self, *args, **options):
        from approvals.models import ApprovalRequest
        from approvals.cms_bridge import sync_receipt_to_cms

        dry_run = options["dry_run"]
        qs = ApprovalRequest.objects.filter(state__in=FINAL_STATES)

        if not qs.exists():
            self.stdout.write("No finalised requests found.")
            return

        self.stdout.write(f"Found {qs.count()} finalised request(s).")
        ok = fail = 0

        for req in qs.iterator():
            label = f"#{req.id} {req.service_name or req.title!r} [{req.state}]"
            if dry_run:
                self.stdout.write(f"  would sync {label}")
                continue
            try:
                sync_receipt_to_cms(req)
                self.stdout.write(self.style.SUCCESS(f"  synced {label}"))
                ok += 1
            except Exception as exc:
                self.stderr.write(f"  FAILED {label}: {exc}")
                fail += 1

        if not dry_run:
            self.stdout.write(f"\nDone — {ok} synced, {fail} failed.")
