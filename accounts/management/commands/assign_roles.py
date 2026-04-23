"""
Management command: python manage.py assign_roles

Assigns employee / manager roles to existing users without creating any new
users.  No user is given both roles.

  Employees  : alice, george, shivansh, frank
  Managers   : bob, carol, dave, eve
  Unmodified : admin@bv.com
"""
from django.core.management.base import BaseCommand
from django.db import transaction


# --- role assignments ----------------------------------------------------------
MANAGERS = [
    'bob@bv.com',
    'carol@bv.com',
    'dave@bv.com',
    'eve@bv.com',
]

# Each tuple is (employee_email, manager_email)
EMPLOYEES = [
    ('alice@bv.com',              'bob@bv.com'),
    ('george@bv.com',             'carol@bv.com'),
    ('shivansh@cadienttalent.com','dave@bv.com'),
    ('frank@bv.com',              'eve@bv.com'),
]
# ------------------------------------------------------------------------------


class Command(BaseCommand):
    help = 'Assign employee/manager roles to existing users (no new users created)'

    def handle(self, *args, **options):
        from accounts.models import CustomUser

        all_employee_emails = {e for e, _ in EMPLOYEES}
        overlap = all_employee_emails & set(MANAGERS)
        if overlap:
            self.stderr.write(self.style.ERROR(
                f'Overlap detected between employees and managers: {overlap}'
            ))
            return

        with transaction.atomic():
            manager_users = self._assign_managers()
            employee_users = self._assign_employees(manager_users)

        self._print_summary(manager_users, employee_users)

    # ------------------------------------------------------------------
    def _assign_managers(self):
        from accounts.models import CustomUser

        manager_users = {}
        self.stdout.write('\n--- Assigning managers ---')
        for email in MANAGERS:
            try:
                user = CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                self.stderr.write(self.style.WARNING(f'  SKIP  {email} - not found'))
                continue

            user.role = 'manager'
            user.reports_to = None   # managers have no subordinate manager here
            user.save(update_fields=['role', 'reports_to'])
            manager_users[email] = user
            self.stdout.write(f'  OK    {email} -> manager')

        return manager_users

    def _assign_employees(self, manager_users):
        from accounts.models import CustomUser

        employee_users = []
        self.stdout.write('\n--- Assigning employees ---')
        for emp_email, mgr_email in EMPLOYEES:
            try:
                user = CustomUser.objects.get(email=emp_email)
            except CustomUser.DoesNotExist:
                self.stderr.write(self.style.WARNING(f'  SKIP  {emp_email} - not found'))
                continue

            manager = manager_users.get(mgr_email)
            user.role = 'employee'
            user.reports_to = manager   # None if manager wasn't found
            user.save(update_fields=['role', 'reports_to'])
            employee_users.append((user, manager))
            mgr_label = manager.get_full_name() or mgr_email if manager else '(no manager)'
            self.stdout.write(f'  OK    {emp_email} -> employee, reports to {mgr_label}')

        return employee_users

    # ------------------------------------------------------------------
    def _print_summary(self, manager_users, employee_users):
        self.stdout.write('\n' + '=' * 55)
        self.stdout.write(self.style.SUCCESS('MANAGERS'))
        self.stdout.write('=' * 55)
        for email, user in manager_users.items():
            name = user.get_full_name() or '(no name)'
            self.stdout.write(f'  {name:<20} {email}')

        self.stdout.write('\n' + '=' * 55)
        self.stdout.write(self.style.SUCCESS('EMPLOYEES'))
        self.stdout.write('=' * 55)
        for user, manager in employee_users:
            name = user.get_full_name() or '(no name)'
            if manager:
                mgr_name = manager.get_full_name() or manager.email
                self.stdout.write(f'  {name:<20} {user.email}  ->  reports to {mgr_name}')
            else:
                self.stdout.write(f'  {name:<20} {user.email}  ->  (no manager assigned)')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Done.'))
