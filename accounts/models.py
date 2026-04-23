from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    EMPLOYEE = 'employee', 'Employee'
    MANAGER = 'manager', 'Manager'
    FINANCE = 'finance', 'Finance'
    IT = 'it', 'IT'
    ADMIN = 'admin', 'Admin'


class CustomUser(AbstractUser):
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.EMPLOYEE,
    )
    reports_to = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reports',
    )
    offboarded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.get_full_name() or self.email} ({self.get_role_display()})'

    @property
    def is_c_suite(self):
        """C-suite: no manager (reports_to is None)."""
        return self.reports_to is None

    @property
    def display_name(self):
        return self.get_full_name() or self.email
