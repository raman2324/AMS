from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from approvals.models import ApprovalRequest
from notifications.services import send_notification


class Command(BaseCommand):
    help = 'Send renewal reminders for subscriptions expiring within 10 days'

    def handle(self, *args, **options):
        today = timezone.now().date()
        reminder_date = today + timedelta(days=10)

        expiring_soon = ApprovalRequest.objects.filter(
            state='active',
            request_type='subscription',
            expires_on__lte=reminder_date,
            expires_on__gte=today,
        ).select_related('submitted_by')

        count = 0
        for req in expiring_soon:
            sent = send_notification(
                subject_id=req.id,
                action_type='renewal_reminder_10day',
                target_date=today,
                recipient=req.submitted_by,
                subject=f'Your subscription "{req.service_name}" expires in 10 days',
                body=(
                    f'Hi {req.submitted_by.display_name},\n\n'
                    f'Your subscription to {req.service_name} expires on {req.expires_on}.\n'
                    f'Please log in to AMS and initiate a renewal before it expires.\n\n'
                    f'Link: http://127.0.0.1:8000/requests/{req.id}/'
                ),
            )
            if sent:
                count += 1

        self.stdout.write(self.style.SUCCESS(f'Sent {count} renewal reminders.'))
