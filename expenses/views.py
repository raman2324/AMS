from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages

from approvals.models import ApprovalRequest, RequestType
from approvals.services import submit


@login_required
def expense_new(request):
    """Create a new misc expense request."""
    if request.method == 'POST':
        try:
            obj = ApprovalRequest(
                request_type=RequestType.MISC_EXPENSE,
                submitted_by=request.user,
                expense_type=request.POST.get('expense_type', ''),
                amount_type=request.POST.get('amount_type', ''),
                cost=request.POST.get('cost') or None,
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
    """List user's expense requests."""
    expenses = ApprovalRequest.objects.filter(
        submitted_by=request.user,
        request_type=RequestType.MISC_EXPENSE,
    ).order_by('-created_at')
    return render(request, 'expenses/expense_list.html', {'expenses': expenses})
