from django.db import models
from django.core.exceptions import PermissionDenied
from accounts.models import CustomUser


class AuditLog(models.Model):
    actor = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_actions',
    )
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=50)  # 'request', 'subscription', 'user'
    target_id = models.IntegerField()
    notes = models.TextField(blank=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.actor} → {self.action} on {self.target_type}#{self.target_id}'

    def delete(self, *args, **kwargs):
        raise PermissionDenied('AuditLog entries are append-only and cannot be deleted.')
