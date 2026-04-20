from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'role', 'reports_to', 'is_active')
    list_filter = ('role', 'is_active')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)

    fieldsets = UserAdmin.fieldsets + (
        ('AMS', {'fields': ('role', 'reports_to', 'offboarded_at')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('AMS', {'fields': ('role', 'reports_to')}),
    )
