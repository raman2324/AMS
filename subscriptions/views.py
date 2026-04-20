from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from datetime import timedelta

from approvals.models import ApprovalRequest, RequestType
from accounts.models import Role
from .services import get_subscriptions_for_user


@login_required
def dashboard(request):
    """Subscription dashboard."""
    subscriptions = get_subscriptions_for_user(request.user)

    today = timezone.now().date()
    renewal_threshold = today + timedelta(days=14)

    active = subscriptions.filter(state='active')
    active_pending = subscriptions.filter(state='active_pending_renewal')
    renewing = subscriptions.filter(state='renewing')
    terminated = subscriptions.filter(state='terminated')
    pending = subscriptions.filter(state__in=['pending_manager', 'pending_finance', 'provisioning'])

    # Subscriptions eligible for renewal (expiring within 14 days)
    renewal_eligible = subscriptions.filter(
        state='active',
        expires_on__lte=renewal_threshold,
        expires_on__gte=today,
    )

    return render(request, 'subscriptions/dashboard.html', {
        'active': active,
        'active_pending': active_pending,
        'renewing': renewing,
        'terminated': terminated,
        'pending': pending,
        'renewal_eligible': renewal_eligible,
        'total_active': active.count() + active_pending.count(),
        'today': today,
        'renewal_threshold': renewal_threshold,
    })
