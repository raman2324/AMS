from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'actor', 'action', 'target_type', 'target_id', 'notes', 'created_at')
    list_filter = ('action', 'target_type', 'created_at')
    search_fields = ('actor__email', 'action', 'notes')
    readonly_fields = ('actor', 'action', 'target_type', 'target_id', 'notes', 'payload', 'created_at')

    def has_delete_permission(self, request, obj=None):
        return False
