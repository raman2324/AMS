from django.db import models


class NotificationSent(models.Model):
    subject_id = models.IntegerField()
    action_type = models.CharField(max_length=100)
    target_date = models.DateField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('subject_id', 'action_type', 'target_date')]

    def __str__(self):
        return f'Notification: {self.action_type} for subject {self.subject_id} on {self.target_date}'
