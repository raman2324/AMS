from django.contrib import admin
from .models import ApprovalRequest


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'request_type', 'service_name', 'submitted_by',
        'current_approver', 'state', 'cost', 'created_at',
    )
    list_filter = ('state', 'request_type', 'billing_period')
    search_fields = ('service_name', 'vendor', 'submitted_by__email')
    readonly_fields = ('state', 'created_at', 'updated_at')
    raw_id_fields = ('submitted_by', 'current_approver')
