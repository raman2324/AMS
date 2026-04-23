import csv
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

from .models import AuditLog
from accounts.models import CustomUser, Role


def require_finance_or_admin(user):
    if user.role not in (Role.ADMIN,):
        raise PermissionDenied('Admin role required.')


@login_required
def audit_log(request):
    require_finance_or_admin(request.user)

    logs = AuditLog.objects.select_related('actor').all()

    # Filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    action_type = request.GET.get('action_type')
    actor_id = request.GET.get('actor_id')

    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)
    if date_to:
        logs = logs.filter(created_at__date__lte=date_to)
    if action_type:
        logs = logs.filter(action__icontains=action_type)
    if actor_id:
        logs = logs.filter(actor_id=actor_id)

    logs = logs[:500]

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="audit_log.csv"'
        writer = csv.writer(response)
        writer.writerow(['ID', 'Actor', 'Action', 'Target Type', 'Target ID', 'Notes', 'Created At'])
        for log in logs:
            writer.writerow([
                log.id,
                log.actor.email if log.actor else 'system',
                log.action,
                log.target_type,
                log.target_id,
                log.notes,
                log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            ])
        return response

    actors = CustomUser.objects.filter(is_active=True).order_by('email')
    unique_actions = AuditLog.objects.values_list('action', flat=True).distinct().order_by('action')

    return render(request, 'admin_ams/audit.html', {
        'logs': logs,
        'actors': actors,
        'unique_actions': unique_actions,
        'filters': {
            'date_from': date_from or '',
            'date_to': date_to or '',
            'action_type': action_type or '',
            'actor_id': actor_id or '',
        },
    })


@login_required
def my_audit_log(request):
    logs = (
        AuditLog.objects
        .filter(actor=request.user)
        .select_related('actor')
        .order_by('-created_at')[:200]
    )
    return render(request, 'admin_ams/my_audit.html', {'logs': logs})


@login_required
def offboard(request):
    require_finance_or_admin(request.user)

    from accounts.services import offboard_employee, get_offboard_preview

    active_employees = CustomUser.objects.filter(
        is_active=True
    ).exclude(id=request.user.id).order_by('email')

    result = None
    preview = None
    selected_user = None

    if request.method == 'POST':
        action = request.POST.get('action')
        user_id = request.POST.get('user_id')
        last_day_str = request.POST.get('last_day', '')

        try:
            selected_user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            from django.contrib import messages
            messages.error(request, 'User not found.')
            return redirect('audit:offboard')

        if action == 'preview':
            preview = get_offboard_preview(selected_user)
        elif action == 'confirm':
            from datetime import date
            last_day = date.fromisoformat(last_day_str) if last_day_str else date.today()
            result = offboard_employee(selected_user, last_day=last_day, actor=request.user)
            from django.contrib import messages
            if result.get('already_offboarded'):
                messages.warning(request, f'{selected_user.display_name} was already offboarded.')
            else:
                messages.success(
                    request,
                    f'{selected_user.display_name} offboarded. '
                    f'{len(result["terminated"])} subscriptions terminated, '
                    f'{len(result["reassigned"])} approvals reassigned.'
                )
            return redirect('audit:offboard')

    return render(request, 'admin_ams/offboard.html', {
        'active_employees': active_employees,
        'preview': preview,
        'selected_user': selected_user,
        'result': result,
    })
