"""
Approval workflow service layer.
Every state transition: checks permission → calls FSM → creates AuditLog → sends notification.
"""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from accounts.models import Role


def _get_finance_head():
    """Return first active finance executive (role=FINANCE)."""
    from accounts.models import CustomUser
    return CustomUser.objects.filter(role=Role.FINANCE, is_active=True).first()


def _expiry_from_billing(billing_period, from_date):
    """Return a new expiry date based on billing_period, or None for one_time."""
    from datetime import date
    from calendar import monthrange
    if billing_period == 'monthly':
        m = from_date.month % 12 + 1
        y = from_date.year + (1 if from_date.month == 12 else 0)
        d = min(from_date.day, monthrange(y, m)[1])
        return date(y, m, d)
    if billing_period == 'annual':
        try:
            return from_date.replace(year=from_date.year + 1)
        except ValueError:
            return from_date.replace(year=from_date.year + 1, day=28)
    return None


def _get_finance_head_admin():
    """Return the Finance Head (role=ADMIN, non-superuser) for CC notifications."""
    from accounts.models import CustomUser
    return CustomUser.objects.filter(role=Role.ADMIN, is_active=True, is_superuser=False).first()


def _require_role(actor, *roles):
    if actor.role not in roles:
        raise PermissionDenied(
            f'Role {actor.role} not allowed. Required: {roles}'
        )


@transaction.atomic
def submit(request_obj, actor):
    """
    Submit a new request.
    C-suite (no reports_to) → goes directly to pending_finance.
    Everyone else → pending_manager regardless of request type.
    """
    from audit.models import AuditLog
    from notifications.services import send_notification
    from django.utils import timezone

    is_c_suite = actor.reports_to is None

    if is_c_suite:
        # Skip manager, go straight to finance (C-suite has no reports_to)
        finance_head = _get_finance_head()
        # Use update() to bypass FSM protection for this special submit path
        from approvals.models import ApprovalRequest
        request_obj.current_approver = finance_head
        request_obj.save()
        ApprovalRequest.objects.filter(pk=request_obj.pk).update(state='pending_finance')
        # Re-fetch to get updated state (avoid FSM refresh_from_db restriction)
        request_obj = ApprovalRequest.objects.get(pk=request_obj.pk)
        AuditLog.objects.create(
            actor=actor,
            action='submitted_c_suite',
            target_type='request',
            target_id=request_obj.id,
            notes='C-suite submission: skipped manager approval',
            payload={'finance_approver_id': finance_head.id if finance_head else None},
        )
        if finance_head:
            send_notification(
                subject_id=request_obj.id,
                action_type='pending_finance',
                target_date=timezone.now().date(),
                recipient=finance_head,
                subject=f'New approval needed: {request_obj.title}',
                body=(
                    f'A new {request_obj.get_request_type_display()} request from '
                    f'{actor.display_name} requires your approval.\n\n'
                    f'Service: {request_obj.service_name or "N/A"}\n'
                    f'Cost: {request_obj.cost or "N/A"}\n'
                    f'Justification: {request_obj.justification}'
                ),
            )
    else:
        # Regular employee → manager approval.
        # Use the approver already set on the object (chosen on the form), else fall back to reports_to.
        manager = request_obj.current_approver or actor.reports_to
        request_obj.current_approver = manager
        request_obj.save()
        AuditLog.objects.create(
            actor=actor,
            action='submitted',
            target_type='request',
            target_id=request_obj.id,
            notes='Submitted for manager approval',
            payload={'manager_id': manager.id if manager else None},
        )
        if manager:
            send_notification(
                subject_id=request_obj.id,
                action_type='pending_manager',
                target_date=timezone.now().date(),
                recipient=manager,
                subject=f'Approval needed: {request_obj.title}',
                body=(
                    f'{actor.display_name} has submitted a '
                    f'{request_obj.get_request_type_display()} request.\n\n'
                    f'Service: {request_obj.service_name or "N/A"}\n'
                    f'Cost: {request_obj.cost or "N/A"}\n'
                    f'Justification: {request_obj.justification}'
                ),
            )

    return request_obj


@transaction.atomic
def manager_approve(request_obj, actor, comment='', finance_user_id=None):
    """Manager approves → moves to pending_finance, routed to selected finance executive."""
    from audit.models import AuditLog
    from notifications.services import send_notification
    from accounts.models import CustomUser
    from django.utils import timezone

    if request_obj.state != 'pending_manager':
        raise PermissionDenied('Request is not in pending_manager state.')
    if actor.role not in (Role.MANAGER, Role.ADMIN) and actor != request_obj.current_approver:
        raise PermissionDenied('You are not the assigned manager approver.')

    # Resolve chosen finance executive, fall back to first active finance user
    finance_exec = None
    if finance_user_id:
        try:
            finance_exec = CustomUser.objects.get(
                id=finance_user_id, role=Role.FINANCE, is_active=True
            )
        except CustomUser.DoesNotExist:
            pass
    if finance_exec is None:
        finance_exec = _get_finance_head()

    request_obj.manager_approve(comment=comment)
    request_obj.current_approver = finance_exec
    request_obj.save()

    AuditLog.objects.create(
        actor=actor,
        action='manager_approved',
        target_type='request',
        target_id=request_obj.id,
        notes=comment or 'Manager approved',
        payload={
            'comment': comment,
            'finance_exec_id': finance_exec.id if finance_exec else None,
        },
    )

    # Notify the assigned finance executive
    if finance_exec:
        send_notification(
            subject_id=request_obj.id,
            action_type='pending_finance_after_manager',
            target_date=timezone.now().date(),
            recipient=finance_exec,
            subject=f'Finance approval needed: {request_obj.title}',
            body=(
                f'Manager {actor.display_name} approved a request from '
                f'{request_obj.submitted_by.display_name} and assigned it to you.\n\n'
                f'Service: {request_obj.service_name or "N/A"}\n'
                f'Cost: {request_obj.cost or "N/A"}\n'
                f'Comment: {comment}'
            ),
        )

    # CC the Finance Head (role=admin, non-superuser) with a copy notification
    finance_head = _get_finance_head_admin()
    if finance_head and finance_head != finance_exec:
        send_notification(
            subject_id=request_obj.id,
            action_type='pending_finance_head_cc',
            target_date=timezone.now().date(),
            recipient=finance_head,
            subject=f'[CC] Finance approval in progress: {request_obj.title}',
            body=(
                f'CC: Manager {actor.display_name} approved a request from '
                f'{request_obj.submitted_by.display_name}.\n'
                f'Assigned to finance: {finance_exec.display_name if finance_exec else "N/A"}\n\n'
                f'Service: {request_obj.service_name or "N/A"}\n'
                f'Cost: {request_obj.cost or "N/A"}\n'
                f'Comment: {comment}'
            ),
        )

    return request_obj


@transaction.atomic
def manager_reject(request_obj, actor, reason=''):
    """Manager rejects."""
    from audit.models import AuditLog
    from notifications.services import send_notification
    from django.utils import timezone

    if request_obj.state != 'pending_manager':
        raise PermissionDenied('Request is not in pending_manager state.')

    request_obj.manager_reject(reason=reason)
    request_obj.current_approver = None
    request_obj.save()

    AuditLog.objects.create(
        actor=actor,
        action='manager_rejected',
        target_type='request',
        target_id=request_obj.id,
        notes=reason or 'Manager rejected',
        payload={'reason': reason},
    )

    send_notification(
        subject_id=request_obj.id,
        action_type='rejected_by_manager',
        target_date=timezone.now().date(),
        recipient=request_obj.submitted_by,
        subject=f'Request rejected: {request_obj.title}',
        body=(
            f'Your {request_obj.get_request_type_display()} request was rejected by '
            f'{actor.display_name}.\n\nReason: {reason}'
        ),
    )

    return request_obj


@transaction.atomic
def finance_approve(request_obj, actor, comment=''):
    """Finance approves → provisioning (subscription) or approved (expense)."""
    from audit.models import AuditLog
    from notifications.services import send_notification
    from django.utils import timezone
    from accounts.models import CustomUser

    if request_obj.state != 'pending_finance':
        raise PermissionDenied('Request is not in pending_finance state.')
    _require_role(actor, Role.FINANCE, Role.ADMIN)

    if request_obj.request_type == 'subscription':
        request_obj.finance_approve_subscription(comment=comment)
        # Assign to IT for provisioning
        it_user = CustomUser.objects.filter(role=Role.IT, is_active=True).first()
        request_obj.current_approver = it_user
        action = 'finance_approved_subscription'
        next_state_msg = 'moved to provisioning'
    else:
        request_obj.finance_approve_expense(comment=comment)
        request_obj.current_approver = None
        action = 'finance_approved_expense'
        next_state_msg = 'approved'

    request_obj.save()

    AuditLog.objects.create(
        actor=actor,
        action=action,
        target_type='request',
        target_id=request_obj.id,
        notes=comment or f'Finance approved, {next_state_msg}',
        payload={'comment': comment},
    )

    send_notification(
        subject_id=request_obj.id,
        action_type='finance_approved',
        target_date=timezone.now().date(),
        recipient=request_obj.submitted_by,
        subject=f'Request approved: {request_obj.title}',
        body=(
            f'Your {request_obj.get_request_type_display()} request has been approved by finance.\n\n'
            f'Comment: {comment}\nStatus: {next_state_msg}'
        ),
    )

    return request_obj


@transaction.atomic
def finance_reject(request_obj, actor, reason=''):
    """Finance rejects."""
    from audit.models import AuditLog
    from notifications.services import send_notification
    from django.utils import timezone

    if request_obj.state != 'pending_finance':
        raise PermissionDenied('Request is not in pending_finance state.')
    _require_role(actor, Role.FINANCE, Role.ADMIN)

    request_obj.finance_reject(reason=reason)
    request_obj.current_approver = None
    request_obj.save()

    AuditLog.objects.create(
        actor=actor,
        action='finance_rejected',
        target_type='request',
        target_id=request_obj.id,
        notes=reason or 'Finance rejected',
        payload={'reason': reason},
    )

    send_notification(
        subject_id=request_obj.id,
        action_type='rejected_by_finance',
        target_date=timezone.now().date(),
        recipient=request_obj.submitted_by,
        subject=f'Request rejected by finance: {request_obj.title}',
        body=(
            f'Your {request_obj.get_request_type_display()} request was rejected by finance.\n\n'
            f'Reason: {reason}'
        ),
    )

    return request_obj


@transaction.atomic
def it_provision(request_obj, actor, vendor_account_id, billing_start):
    """IT provisions the subscription."""
    from audit.models import AuditLog
    from notifications.services import send_notification
    from django.utils import timezone

    if request_obj.state != 'provisioning':
        raise PermissionDenied('Request is not in provisioning state.')
    _require_role(actor, Role.IT, Role.ADMIN)

    request_obj.it_provision(
        vendor_account_id=vendor_account_id,
        billing_start=billing_start,
    )
    request_obj.current_approver = None
    new_expiry = _expiry_from_billing(request_obj.billing_period, billing_start)
    if new_expiry:
        request_obj.expires_on = new_expiry
    request_obj.save()

    AuditLog.objects.create(
        actor=actor,
        action='it_provisioned',
        target_type='request',
        target_id=request_obj.id,
        notes=f'Provisioned: account={vendor_account_id}, billing_start={billing_start}',
        payload={
            'vendor_account_id': vendor_account_id,
            'billing_start': str(billing_start),
        },
    )

    send_notification(
        subject_id=request_obj.id,
        action_type='provisioned',
        target_date=timezone.now().date(),
        recipient=request_obj.submitted_by,
        subject=f'Subscription provisioned: {request_obj.title}',
        body=(
            f'Your subscription to {request_obj.service_name} is now active.\n\n'
            f'Account ID: {vendor_account_id}\nBilling starts: {billing_start}'
        ),
    )

    return request_obj


@transaction.atomic
def initiate_renewal(request_obj, actor):
    """Move active subscription to renewal workflow."""
    from audit.models import AuditLog

    if request_obj.state == 'active':
        request_obj.extend_pending()
        request_obj.save()
        AuditLog.objects.create(
            actor=actor,
            action='renewal_initiated',
            target_type='request',
            target_id=request_obj.id,
            notes='Subscription marked active_pending_renewal',
        )
    elif request_obj.state == 'active_pending_renewal':
        finance_head = _get_finance_head()
        request_obj.start_renewal()
        request_obj.current_approver = finance_head
        request_obj.save()
        AuditLog.objects.create(
            actor=actor,
            action='renewal_submitted',
            target_type='request',
            target_id=request_obj.id,
            notes='Renewal submitted for finance approval',
            payload={'finance_approver_id': finance_head.id if finance_head else None},
        )

    return request_obj


@transaction.atomic
def complete_renewal(request_obj, actor, approved=True, reason=''):
    """Finance approves or rejects a renewal."""
    from audit.models import AuditLog
    from notifications.services import send_notification
    from django.utils import timezone

    if request_obj.state != 'renewing':
        raise PermissionDenied('Request is not in renewing state.')
    _require_role(actor, Role.FINANCE, Role.ADMIN)

    if approved:
        request_obj.renewal_approved()
        request_obj.current_approver = None
        new_expiry = _expiry_from_billing(request_obj.billing_period, timezone.now().date())
        if new_expiry:
            request_obj.expires_on = new_expiry
        request_obj.save()
        AuditLog.objects.create(
            actor=actor,
            action='renewal_approved',
            target_type='request',
            target_id=request_obj.id,
            notes='Renewal approved by finance',
        )
        send_notification(
            subject_id=request_obj.id,
            action_type='renewal_approved',
            target_date=timezone.now().date(),
            recipient=request_obj.submitted_by,
            subject=f'Renewal approved: {request_obj.title}',
            body=f'Your subscription renewal for {request_obj.service_name} has been approved.',
        )
    else:
        request_obj.renewal_rejected(reason=reason)
        request_obj.current_approver = None
        request_obj.save()
        AuditLog.objects.create(
            actor=actor,
            action='renewal_rejected',
            target_type='request',
            target_id=request_obj.id,
            notes=reason or 'Renewal rejected by finance',
            payload={'reason': reason},
        )
        send_notification(
            subject_id=request_obj.id,
            action_type='renewal_rejected',
            target_date=timezone.now().date(),
            recipient=request_obj.submitted_by,
            subject=f'Renewal rejected: {request_obj.title}',
            body=f'Your subscription renewal was rejected.\nReason: {reason}',
        )

    return request_obj


@transaction.atomic
def terminate_request(request_obj, actor, reason=''):
    """Terminate an active subscription/approved expense."""
    from audit.models import AuditLog

    request_obj.terminate(reason=reason)
    request_obj.current_approver = None
    request_obj.save()

    AuditLog.objects.create(
        actor=actor,
        action='terminated',
        target_type='request',
        target_id=request_obj.id,
        notes=reason or 'Terminated',
        payload={'reason': reason},
    )

    return request_obj
