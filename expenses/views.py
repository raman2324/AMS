from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages

from approvals.models import ApprovalRequest, RequestType, RequestCategory
from approvals.services import submit


@login_required
def expense_new(request):
    """Create a new misc expense request (one-off or recurring)."""
    if request.method == 'POST':
        request_category = request.POST.get('request_category', '')
        if request_category not in (RequestCategory.ONE_OFF, RequestCategory.RECURRING):
            messages.error(request, 'Please select One-off or Recurring.')
            return redirect('expenses:expense_new')

        try:
            cost_str = request.POST.get('cost', '').strip()
            try:
                cost = Decimal(cost_str) if cost_str else None
            except InvalidOperation:
                cost = None

            obj = ApprovalRequest(
                request_type=RequestType.MISC_EXPENSE,
                request_category=request_category,
                submitted_by=request.user,
                expense_type=request_category,  # one_off / recurring maps directly
                amount_type=request.POST.get('amount_type', ''),
                cost=cost,
                justification=request.POST.get('justification', '').strip(),
            )
            if 'receipt' in request.FILES:
                obj.receipt = request.FILES['receipt']
            obj.save()
            obj = submit(obj, actor=request.user)
            messages.success(
                request,
                f'Expense request #{obj.id} submitted. State: {obj.state_display}'
            )
            return redirect('approvals:request_detail', pk=obj.pk)
        except Exception as e:
            messages.error(request, f'Error: {e}')

    return render(request, 'expenses/expense_new.html')


@login_required
def expense_list(request):
    """List user's expense requests, grouped by state."""
    base_qs = ApprovalRequest.objects.filter(
        submitted_by=request.user,
        request_type=RequestType.MISC_EXPENSE,
    ).select_related('current_approver').order_by('-created_at')

    return render(request, 'expenses/expense_list.html', {
        'pending':    base_qs.filter(state__in=['pending_manager', 'pending_finance']),
        'approved':   base_qs.filter(state='approved'),
        'rejected':   base_qs.filter(state__in=['rejected_manager', 'rejected_finance']),
        'terminated': base_qs.filter(state='terminated'),
        'total':      base_qs.count(),
    })
