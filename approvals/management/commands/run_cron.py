"""
Management command: python manage.py run_cron

Checks:
1. Subscriptions expiring in 14 days → send renewal reminder (idempotent)
2. Subscriptions in 'renewing' state past their expires_on → move to active_pending_renewal
3. Subscriptions in 'active_pending_renewal' past 30 days → escalate to finance
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Run scheduled cron tasks: renewal reminders, expiry checks, escalations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would happen without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = timezone.now().date()

        self.stdout.write(self.style.NOTICE(f'[run_cron] Starting cron run for {today}'))

        self._check_renewal_reminders(today, dry_run)
        self._check_expired_renewing(today, dry_run)
        self._check_escalations(today, dry_run)

        self.stdout.write(self.style.SUCCESS('[run_cron] Done.'))

    def _check_renewal_reminders(self, today, dry_run):
        """Send renewal reminders for subscriptions expiring within 14 days."""
        from approvals.models import ApprovalRequest
        from notifications.services import send_notification

        threshold = today + timedelta(days=14)
        upcoming = ApprovalRequest.objects.filter(
            request_type='subscription',
            state='active',
            expires_on__lte=threshold,
            expires_on__gte=today,
        ).select_related('submitted_by')

        self.stdout.write(f'[run_cron] Renewal reminders: {upcoming.count()} subscriptions expiring within 14 days')

        for req in upcoming:
            days_left = (req.expires_on - today).days
            self.stdout.write(f'  >> {req.service_name} (id={req.id}) expires in {days_left} days')

            if not dry_run:
                sent = send_notification(
                    subject_id=req.id,
                    action_type='renewal_reminder_14d',
                    target_date=req.expires_on,
                    recipient=req.submitted_by,
                    subject=f'Renewal reminder: {req.service_name} expires in {days_left} days',
                    body=(
                        f'Your subscription to {req.service_name} expires on {req.expires_on} '
                        f'({days_left} days from now).\n\n'
                        f'Please visit the AMS portal to initiate renewal.'
                    ),
                )
                if sent:
                    self.stdout.write(self.style.SUCCESS(f'    Reminder sent to {req.submitted_by.email}'))
                else:
                    self.stdout.write(f'    Reminder already sent (idempotent)')

    def _check_expired_renewing(self, today, dry_run):
        """
        Subscriptions in 'renewing' state where expires_on < today
        → transition back to active_pending_renewal (renewal in progress, extend notice).
        """
        from approvals.models import ApprovalRequest

        expired_renewing = ApprovalRequest.objects.filter(
            request_type='subscription',
            state='renewing',
            expires_on__lt=today,
        )

        self.stdout.write(f'[run_cron] Expired-while-renewing: {expired_renewing.count()} subscriptions')

        for req in expired_renewing:
            self.stdout.write(f'  >> {req.service_name} (id={req.id}) expired on {req.expires_on} while renewing')
            if not dry_run:
                # Already in renewing, just log a reminder
                from notifications.services import send_notification
                from accounts.models import Role, CustomUser
                finance = CustomUser.objects.filter(role=Role.FINANCE, is_active=True).first()
                if finance:
                    send_notification(
                        subject_id=req.id,
                        action_type='renewal_overdue_finance',
                        target_date=today,
                        recipient=finance,
                        subject=f'Renewal overdue: {req.service_name}',
                        body=(
                            f'Subscription {req.service_name} (id={req.id}) for '
                            f'{req.submitted_by.display_name} has passed its expiry date '
                            f'({req.expires_on}) and is still awaiting renewal approval.'
                        ),
                    )

    def _check_escalations(self, today, dry_run):
        """
        Subscriptions in active_pending_renewal where expires_on < today - 30
        → escalate to finance.
        """
        from approvals.models import ApprovalRequest
        from notifications.services import send_notification
        from accounts.models import Role, CustomUser

        cutoff = today - timedelta(days=30)
        overdue = ApprovalRequest.objects.filter(
            request_type='subscription',
            state='active_pending_renewal',
            expires_on__lt=cutoff,
        ).select_related('submitted_by')

        self.stdout.write(f'[run_cron] Escalations: {overdue.count()} subscriptions overdue by 30+ days')

        finance = CustomUser.objects.filter(role=Role.FINANCE, is_active=True).first()

        for req in overdue:
            days_overdue = (today - req.expires_on).days
            self.stdout.write(f'  >> {req.service_name} (id={req.id}) overdue by {days_overdue} days')

            if not dry_run and finance:
                send_notification(
                    subject_id=req.id,
                    action_type='renewal_escalation_30d',
                    target_date=today,
                    recipient=finance,
                    subject=f'ESCALATION: {req.service_name} overdue renewal ({days_overdue} days)',
                    body=(
                        f'Subscription {req.service_name} for {req.submitted_by.display_name} '
                        f'expired on {req.expires_on} ({days_overdue} days ago) '
                        f'and is still in active_pending_renewal state.\n\n'
                        f'Please take action immediately.'
                    ),
                )
                self.stdout.write(self.style.WARNING(f'    Escalation sent to {finance.email}'))
