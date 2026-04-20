from django.core.mail import send_mail
from django.conf import settings


def send_notification(subject_id, action_type, target_date, recipient, subject, body):
    """
    Idempotent notification: won't send same (subject_id, action_type, target_date) twice.
    Uses console email backend for prototype.
    """
    from .models import NotificationSent

    sent, created = NotificationSent.objects.get_or_create(
        subject_id=subject_id,
        action_type=action_type,
        target_date=target_date,
    )

    if created:
        # Send email
        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f'[notifications] Email send failed: {e}')

    return created
