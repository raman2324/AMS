"""
Management command: python manage.py seed

Creates 6 test users for development.
"""
from django.core.management.base import BaseCommand
from django.db import transaction


USERS = [
    {
        'email': 'frank@bv.com',
        'username': 'frank',
        'first_name': 'Frank',
        'last_name': 'Admin',
        'role': 'admin',
        'reports_to_email': None,
    },
    {
        'email': 'carol@bv.com',
        'username': 'carol',
        'first_name': 'Carol',
        'last_name': 'Finance',
        'role': 'finance',
        'reports_to_email': None,
    },
    {
        'email': 'dave@bv.com',
        'username': 'dave',
        'first_name': 'Dave',
        'last_name': 'IT',
        'role': 'it',
        'reports_to_email': None,
    },
    {
        'email': 'eve@bv.com',
        'username': 'eve',
        'first_name': 'Eve',
        'last_name': 'Finance',
        'role': 'finance',
        'reports_to_email': None,
    },
    {
        'email': 'bob@bv.com',
        'username': 'bob',
        'first_name': 'Bob',
        'last_name': 'Manager',
        'role': 'manager',
        'reports_to_email': 'frank@bv.com',
    },
    {
        'email': 'alice@bv.com',
        'username': 'alice',
        'first_name': 'Alice',
        'last_name': 'Employee',
        'role': 'employee',
        'reports_to_email': 'bob@bv.com',
    },
]


class Command(BaseCommand):
    help = 'Seed 6 test users (alice, bob, carol, dave, eve, frank)'

    def handle(self, *args, **options):
        from accounts.models import CustomUser

        with transaction.atomic():
            created_users = {}

            # First pass: create users without reports_to
            for data in USERS:
                reports_to_email = data['reports_to_email']
                user, created = CustomUser.objects.get_or_create(
                    email=data['email'],
                    defaults={
                        'username': data['username'],
                        'first_name': data['first_name'],
                        'last_name': data['last_name'],
                        'role': data['role'],
                    },
                )
                if created:
                    user.set_password('pass1234')
                    user.save()
                    self.stdout.write(f'  Created {user.email}')
                else:
                    self.stdout.write(f'  Exists  {user.email}')
                created_users[data['email']] = (user, reports_to_email)

            # Second pass: set reports_to
            for email, (user, reports_to_email) in created_users.items():
                if reports_to_email:
                    manager = created_users[reports_to_email][0]
                    if user.reports_to_id != manager.pk:
                        user.reports_to = manager
                        user.save(update_fields=['reports_to'])

        self.stdout.write(self.style.SUCCESS('Done. All passwords: pass1234'))
        self.stdout.write('  alice@bv.com  — Employee, reports to bob')
        self.stdout.write('  bob@bv.com    — Manager, reports to frank')
        self.stdout.write('  carol@bv.com  — Finance')
        self.stdout.write('  dave@bv.com   — IT')
        self.stdout.write('  eve@bv.com    — HR')
        self.stdout.write('  frank@bv.com  — Admin (C-suite)')
