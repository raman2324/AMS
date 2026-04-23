from django.db import transaction
from django.utils import timezone


@transaction.atomic
def offboard_employee(user, last_day, actor):
    """
    Offboard an employee:
    1. Terminate all active subscriptions
    2. Reassign pending approvals where this user is current_approver
    3. Mark user inactive
    """
    if not user.is_active or user.offboarded_at:
        return {'terminated': [], 'reassigned': [], 'already_offboarded': True}

    # Import here to avoid circular imports
    from approvals.models import ApprovalRequest
    from audit.models import AuditLog

    terminated = []
    reassigned = []

    # 1. Terminate all active subscriptions
    active_requests = ApprovalRequest.objects.filter(
        submitted_by=user,
        state__in=['active', 'active_pending_renewal', 'renewing'],
        request_type='subscription',
    )
    for req in active_requests:
        req.terminate(reason=f'Finance offboard: {user.display_name}')
        req.save()
        AuditLog.objects.create(
            actor=actor,
            action='finance_offboarded',
            target_type='request',
            target_id=req.id,
            notes=f'Subscription terminated due to Finance offboard of {user.display_name}',
            payload={'user_id': user.id, 'last_day': str(last_day)},
        )
        terminated.append(req)

    # 2. Reassign pending approvals where this user is current_approver
    pending = ApprovalRequest.objects.filter(
        current_approver=user,
        state__in=['pending_manager', 'pending_finance'],
    )
    for req in pending:
        new_approver = user.reports_to if (user.reports_to and user.reports_to.is_active) else None
        old_approver = req.current_approver
        req.current_approver = new_approver
        req.save()
        AuditLog.objects.create(
            actor=actor,
            action='approver_reassigned',
            target_type='request',
            target_id=req.id,
            notes=(
                f'Approver reassigned from {old_approver.display_name} to '
                f'{new_approver.display_name if new_approver else "admin queue"}'
            ),
            payload={
                'old_approver_id': old_approver.id,
                'new_approver_id': new_approver.id if new_approver else None,
            },
        )
        reassigned.append(req)

    # 3. Mark user inactive
    user.is_active = False
    user.offboarded_at = timezone.now()
    user.save()

    AuditLog.objects.create(
        actor=actor,
        action='employee_offboarded',
        target_type='user',
        target_id=user.id,
        notes=f'Employee {user.display_name} offboarded. Last day: {last_day}',
        payload={'last_day': str(last_day)},
    )

    return {
        'terminated': terminated,
        'reassigned': reassigned,
        'already_offboarded': False,
    }


def get_offboard_preview(user):
    """Preview what will happen when this user is offboarded."""
    from approvals.models import ApprovalRequest

    active_subs = ApprovalRequest.objects.filter(
        submitted_by=user,
        state__in=['active', 'active_pending_renewal', 'renewing'],
        request_type='subscription',
    ).select_related('submitted_by')

    pending_approvals = ApprovalRequest.objects.filter(
        current_approver=user,
        state__in=['pending_manager', 'pending_finance'],
    ).select_related('submitted_by')

    return {
        'active_subscriptions': active_subs,
        'pending_approvals': pending_approvals,
        'new_approver': user.reports_to if (user.reports_to and user.reports_to.is_active) else None,
    }
