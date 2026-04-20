from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .models import ApprovalRequest, RequestType, PENDING_STATES
from .services import (
    submit, manager_approve, manager_reject,
    finance_approve, finance_reject, it_provision,
    initiate_renewal, complete_renewal, terminate_request,
)
from accounts.models import Role
from audit.models import AuditLog


@login_required
def request_new(request):
    """Create a new approval request (subscription or misc expense)."""
    if request.method == 'POST':
        req_type = request.POST.get('request_type')
        if req_type not in (RequestType.SUBSCRIPTION, RequestType.MISC_EXPENSE):
            messages.error(request, 'Invalid request type.')
            return redirect('approvals:request_new')

        try:
            obj = ApprovalRequest(
                request_type=req_type,
                submitted_by=request.user,
            )

            if req_type == RequestType.SUBSCRIPTION:
                obj.service_name = request.POST.get('service_name', '').strip()
                obj.vendor = request.POST.get('vendor', '').strip()
                obj.cost = request.POST.get('cost') or None
                obj.billing_period = request.POST.get('billing_period', '')
                obj.justification = request.POST.get('justification', '').strip()
                expires_on = request.POST.get('expires_on', '').strip()
                if expires_on:
                    from datetime import date
                    obj.expires_on = date.fromisoformat(expires_on)
            else:
                obj.expense_type = request.POST.get('expense_type', '')
                obj.amount_type = request.POST.get('amount_type', '')
                obj.cost = request.POST.get('cost') or None
                obj.justification = request.POST.get('justification', '').strip()
                if 'receipt' in request.FILES:
                    obj.receipt = request.FILES['receipt']

            obj.save()
            obj = submit(obj, actor=request.user)
            messages.success(
                request,
                f'Request #{obj.id} submitted successfully. Current state: {obj.state_display}'
            )
            return redirect('approvals:request_detail', pk=obj.pk)

        except Exception as e:
            messages.error(request, f'Error submitting request: {e}')
            return redirect('approvals:request_new')

    return render(request, 'approvals/request_new.html', {
        'request_types': RequestType.choices,
    })


@login_required
def request_detail(request, pk):
    """Show request detail with approval actions."""
    obj = get_object_or_404(ApprovalRequest, pk=pk)

    # Check access: submitter, approver, or admin/finance/hr
    user = request.user
    can_view = (
        obj.submitted_by == user or
        obj.current_approver == user or
        user.role in (Role.ADMIN, Role.FINANCE, Role.HR, Role.IT)
    )
    if not can_view:
        raise PermissionDenied

    audit_logs = AuditLog.objects.filter(
        target_type='request', target_id=obj.id
    ).select_related('actor').order_by('created_at')

    is_approver = (obj.current_approver == user)
    can_manager_approve = is_approver and obj.state == 'pending_manager'
    can_finance_approve = (
        user.role in (Role.FINANCE, Role.ADMIN) and obj.state == 'pending_finance'
    )
    can_provision = (
        user.role in (Role.IT, Role.ADMIN) and obj.state == 'provisioning'
    )
    can_renew = (
        obj.state in ('active', 'active_pending_renewal') and
        obj.request_type == RequestType.SUBSCRIPTION and
        (obj.submitted_by == user or user.role in (Role.ADMIN, Role.FINANCE))
    )
    can_terminate = (
        obj.state in ('active', 'active_pending_renewal', 'renewing', 'provisioning', 'approved') and
        user.role in (Role.ADMIN, Role.FINANCE, Role.HR)
    )

    context = {
        'obj': obj,
        'audit_logs': audit_logs,
        'can_manager_approve': can_manager_approve,
        'can_finance_approve': can_finance_approve,
        'can_provision': can_provision,
        'can_renew': can_renew,
        'can_terminate': can_terminate,
    }

    if request.htmx:
        return render(request, 'approvals/partials/request_detail_body.html', context)
    return render(request, 'approvals/request_detail.html', context)


@login_required
def action_approve(request, pk):
    """HTMX: approve a request (manager or finance depending on state)."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    obj = get_object_or_404(ApprovalRequest, pk=pk)
    comment = request.POST.get('comment', '')

    try:
        if obj.state == 'pending_manager':
            obj = manager_approve(obj, actor=request.user, comment=comment)
        elif obj.state == 'pending_finance':
            obj = finance_approve(obj, actor=request.user, comment=comment)
        elif obj.state == 'renewing':
            obj = complete_renewal(obj, actor=request.user, approved=True)
        else:
            raise PermissionDenied('Cannot approve in current state.')

        messages.success(request, f'Request approved. New state: {obj.state_display}')
    except PermissionDenied as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f'Error: {e}')

    if request.htmx:
        return redirect('approvals:request_detail', pk=pk)
    return redirect('approvals:request_detail', pk=pk)


@login_required
def action_reject(request, pk):
    """HTMX: reject a request."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    obj = get_object_or_404(ApprovalRequest, pk=pk)
    reason = request.POST.get('reason', '')

    try:
        if obj.state == 'pending_manager':
            obj = manager_reject(obj, actor=request.user, reason=reason)
        elif obj.state == 'pending_finance':
            obj = finance_reject(obj, actor=request.user, reason=reason)
        elif obj.state == 'renewing':
            obj = complete_renewal(obj, actor=request.user, approved=False, reason=reason)
        else:
            raise PermissionDenied('Cannot reject in current state.')

        messages.success(request, f'Request rejected. State: {obj.state_display}')
    except PermissionDenied as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f'Error: {e}')

    return redirect('approvals:request_detail', pk=pk)


@login_required
def action_provision(request, pk):
    """IT: provision a subscription."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    obj = get_object_or_404(ApprovalRequest, pk=pk)
    vendor_account_id = request.POST.get('vendor_account_id', '')
    billing_start_str = request.POST.get('billing_start', '')

    try:
        from datetime import date
        billing_start = date.fromisoformat(billing_start_str) if billing_start_str else date.today()
        obj = it_provision(obj, actor=request.user,
                           vendor_account_id=vendor_account_id,
                           billing_start=billing_start)
        messages.success(request, 'Subscription provisioned and now active.')
    except Exception as e:
        messages.error(request, f'Error provisioning: {e}')

    return redirect('approvals:request_detail', pk=pk)


@login_required
def action_renew(request, pk):
    """Initiate renewal for an active subscription."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    obj = get_object_or_404(ApprovalRequest, pk=pk)
    try:
        obj = initiate_renewal(obj, actor=request.user)
        messages.success(request, f'Renewal initiated. State: {obj.state_display}')
    except Exception as e:
        messages.error(request, f'Error: {e}')

    return redirect('approvals:request_detail', pk=pk)


@login_required
def action_terminate(request, pk):
    """Terminate an active subscription."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    obj = get_object_or_404(ApprovalRequest, pk=pk)
    reason = request.POST.get('reason', '')

    try:
        obj = terminate_request(obj, actor=request.user, reason=reason)
        messages.success(request, 'Request terminated.')
    except Exception as e:
        messages.error(request, f'Error: {e}')

    return redirect('approvals:request_detail', pk=pk)


@login_required
def inbox(request):
    """Inbox: requests pending action from the current user."""
    user = request.user

    # Requests where I am the current approver
    my_pending = ApprovalRequest.objects.filter(
        current_approver=user,
        state__in=PENDING_STATES,
    ).select_related('submitted_by', 'current_approver')

    # IT provisioning queue
    it_queue = ApprovalRequest.objects.none()
    if user.role in (Role.IT, Role.ADMIN):
        it_queue = ApprovalRequest.objects.filter(
            state='provisioning',
        ).select_related('submitted_by')

    # Finance renewal queue
    renewal_queue = ApprovalRequest.objects.none()
    if user.role in (Role.FINANCE, Role.ADMIN):
        renewal_queue = ApprovalRequest.objects.filter(
            state='renewing',
        ).select_related('submitted_by', 'current_approver')

    context = {
        'my_pending': my_pending,
        'it_queue': it_queue,
        'renewal_queue': renewal_queue,
    }
    return render(request, 'approvals/inbox.html', context)


@login_required
def my_requests(request):
    """All requests submitted by current user."""
    requests_qs = ApprovalRequest.objects.filter(
        submitted_by=request.user
    ).select_related('submitted_by', 'current_approver')

    return render(request, 'approvals/my_requests.html', {'requests': requests_qs})
