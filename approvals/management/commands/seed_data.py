"""
Management command: python manage.py seed_data

Creates demo users and sample data for the AMS prototype.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import date, timedelta


class Command(BaseCommand):
    help = 'Seed demo users and sample data'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Seeding demo data...'))
        with transaction.atomic():
            self._create_users()
        try:
            self._create_sample_data()
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Sample data skipped due to error: {e}'))
        self.stdout.write(self.style.SUCCESS('Seed data created successfully!'))

    def _create_users(self):
        from accounts.models import CustomUser, Role
        from django.contrib.sites.models import Site

        # Update site
        site, _ = Site.objects.get_or_create(id=1)
        site.domain = 'localhost:8000'
        site.name = 'AMS Prototype'
        site.save()

        users_data = [
            # Django superuser (for /admin)
            {
                'email': 'admin@bv.com',
                'username': 'admin_bv',
                'first_name': 'Admin',
                'last_name': 'User',
                'role': Role.ADMIN,
                'is_staff': True,
                'is_superuser': True,
                'reports_to_email': None,
            },
            # Finance Head (role=admin, non-superuser)
            {
                'email': 'frank@bv.com',
                'username': 'frank',
                'first_name': 'Frank',
                'last_name': 'Head',
                'role': Role.ADMIN,
                'reports_to_email': None,
            },
            # Finance Executives
            {
                'email': 'carol@bv.com',
                'username': 'carol',
                'first_name': 'Carol',
                'last_name': 'Finance',
                'role': Role.FINANCE,
                'reports_to_email': None,
            },
            {
                'email': 'mike@bv.com',
                'username': 'mike',
                'first_name': 'Mike',
                'last_name': 'Finance',
                'role': Role.FINANCE,
                'reports_to_email': None,
            },
            # IT
            {
                'email': 'dave@bv.com',
                'username': 'dave',
                'first_name': 'Dave',
                'last_name': 'IT',
                'role': Role.IT,
                'reports_to_email': None,
            },
            {
                'email': 'eve@bv.com',
                'username': 'eve',
                'first_name': 'Eve',
                'last_name': 'Finance',
                'role': Role.FINANCE,
                'reports_to_email': None,
            },
            # Managers
            {
                'email': 'bob@bv.com',
                'username': 'bob',
                'first_name': 'Bob',
                'last_name': 'Manager',
                'role': Role.MANAGER,
                'reports_to_email': None,
            },
            {
                'email': 'sarah@bv.com',
                'username': 'sarah',
                'first_name': 'Sarah',
                'last_name': 'Manager',
                'role': Role.MANAGER,
                'reports_to_email': None,
            },
            {
                'email': 'raj@bv.com',
                'username': 'raj',
                'first_name': 'Raj',
                'last_name': 'Manager',
                'role': Role.MANAGER,
                'reports_to_email': None,
            },
            # Employees
            {
                'email': 'alice@bv.com',
                'username': 'alice',
                'first_name': 'Alice',
                'last_name': 'Employee',
                'role': Role.EMPLOYEE,
                'reports_to_email': 'bob@bv.com',
            },
            {
                'email': 'john@bv.com',
                'username': 'john',
                'first_name': 'John',
                'last_name': 'Employee',
                'role': Role.EMPLOYEE,
                'reports_to_email': 'bob@bv.com',
            },
            {
                'email': 'priya@bv.com',
                'username': 'priya',
                'first_name': 'Priya',
                'last_name': 'Employee',
                'role': Role.EMPLOYEE,
                'reports_to_email': 'sarah@bv.com',
            },
            # Offboard demo target
            {
                'email': 'george@bv.com',
                'username': 'george',
                'first_name': 'George',
                'last_name': 'Leaving',
                'role': Role.EMPLOYEE,
                'reports_to_email': 'bob@bv.com',
            },
        ]

        created_users = {}
        for data in users_data:
            reports_to_email = data.pop('reports_to_email')
            data['_reports_to_email'] = reports_to_email

            user, created = CustomUser.objects.update_or_create(
                email=data['email'],
                defaults={
                    'username': data['username'],
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                    'role': data['role'],
                    'is_staff': data.get('is_staff', False),
                    'is_superuser': data.get('is_superuser', False),
                }
            )
            if created:
                user.set_password('password123')
                user.save()
                self.stdout.write(f'  Created user: {user.email}')
            else:
                self.stdout.write(f'  Updated user: {user.email}')
            created_users[data['email']] = (user, reports_to_email)

        # Second pass: set reports_to
        for email, (user, reports_to_email) in created_users.items():
            if reports_to_email and reports_to_email in created_users:
                manager = created_users[reports_to_email][0]
                if user.reports_to != manager:
                    user.reports_to = manager
                    user.save()

        self.stdout.write(self.style.SUCCESS('  Users created/updated.'))
        return created_users

    def _create_sample_data(self):
        from accounts.models import CustomUser
        from approvals.models import ApprovalRequest, RequestType, BillingPeriod, ExpenseType, AmountType

        if ApprovalRequest.objects.exists():
            self.stdout.write('  Sample data already exists, skipping.')
            return

        try:
            alice = CustomUser.objects.get(email='alice@bv.com')
            bob = CustomUser.objects.get(email='bob@bv.com')
            carol = CustomUser.objects.get(email='carol@bv.com')
            dave = CustomUser.objects.get(email='dave@bv.com')
            george = CustomUser.objects.get(email='george@bv.com')
        except CustomUser.DoesNotExist as e:
            self.stdout.write(self.style.ERROR(f'User not found: {e}'))
            return

        today = date.today()

        # 1. Active Slack subscription for Alice
        slack, created = ApprovalRequest.objects.get_or_create(
            submitted_by=alice,
            service_name='Slack',
            defaults={
                'request_type': RequestType.SUBSCRIPTION,
                'vendor': 'Salesforce',
                'cost': 12.50,
                'billing_period': BillingPeriod.MONTHLY,
                'justification': 'Team communication tool',
                'expires_on': today + timedelta(days=60),
                'vendor_account_id': 'SLK-ALICE-001',
                'billing_start': today - timedelta(days=30),
            }
        )
        if created:
            ApprovalRequest.objects.filter(pk=slack.pk).update(state='active')
            slack = ApprovalRequest.objects.get(pk=slack.pk)
            self.stdout.write(f'  Created Slack subscription (id={slack.id})')

        # 2. Active Figma subscription for Alice (expiring soon for cron demo)
        figma, created = ApprovalRequest.objects.get_or_create(
            submitted_by=alice,
            service_name='Figma',
            defaults={
                'request_type': RequestType.SUBSCRIPTION,
                'vendor': 'Figma Inc',
                'cost': 15.00,
                'billing_period': BillingPeriod.MONTHLY,
                'justification': 'Design tool for UI work',
                'expires_on': today + timedelta(days=10),
                'vendor_account_id': 'FIG-ALICE-001',
                'billing_start': today - timedelta(days=20),
            }
        )
        if created:
            ApprovalRequest.objects.filter(pk=figma.pk).update(state='active')
            figma = ApprovalRequest.objects.get(pk=figma.pk)
            self.stdout.write(f'  Created Figma subscription (id={figma.id}, expiring soon)')

        # 3. Pending manager approval: GitHub Copilot from Alice
        copilot, created = ApprovalRequest.objects.get_or_create(
            submitted_by=alice,
            service_name='GitHub Copilot',
            defaults={
                'request_type': RequestType.SUBSCRIPTION,
                'vendor': 'GitHub',
                'cost': 19.00,
                'billing_period': BillingPeriod.MONTHLY,
                'justification': 'AI coding assistant to boost developer productivity',
                'expires_on': today + timedelta(days=365),
                'current_approver': bob,
                'state': 'pending_manager',
            }
        )
        if created:
            self.stdout.write(f'  Created GitHub Copilot request (id={copilot.id}, pending_manager)')

        # 4. Misc expense pending for Alice
        expense, created = ApprovalRequest.objects.get_or_create(
            submitted_by=alice,
            expense_type=ExpenseType.ONE_OFF,
            defaults={
                'request_type': RequestType.MISC_EXPENSE,
                'amount_type': AmountType.FIXED,
                'cost': 599.00,
                'justification': 'DjangoCon conference ticket for professional development',
                'current_approver': bob,
                'state': 'pending_manager',
            }
        )
        if created:
            self.stdout.write(f'  Created conference expense (id={expense.id}, pending_manager)')

        # 5. Active subscription for George (to-be-offboarded demo)
        george_sub, created = ApprovalRequest.objects.get_or_create(
            submitted_by=george,
            service_name='Notion',
            defaults={
                'request_type': RequestType.SUBSCRIPTION,
                'vendor': 'Notion Labs',
                'cost': 8.00,
                'billing_period': BillingPeriod.MONTHLY,
                'justification': 'Note-taking and project management',
                'expires_on': today + timedelta(days=90),
                'vendor_account_id': 'NOT-GEORGE-001',
                'billing_start': today - timedelta(days=60),
            }
        )
        if created:
            ApprovalRequest.objects.filter(pk=george_sub.pk).update(state='active')
            george_sub = ApprovalRequest.objects.get(pk=george_sub.pk)
            self.stdout.write(
                f'  Created Notion subscription for George (id={george_sub.id}) - demo offboard target'
            )

        # 6. A subscription in provisioning state (IT queue demo)
        zoom, created = ApprovalRequest.objects.get_or_create(
            submitted_by=alice,
            service_name='Zoom Pro',
            defaults={
                'request_type': RequestType.SUBSCRIPTION,
                'vendor': 'Zoom Video',
                'cost': 14.99,
                'billing_period': BillingPeriod.MONTHLY,
                'justification': 'Video conferencing for remote meetings',
                'expires_on': today + timedelta(days=365),
                'current_approver': dave,
                'finance_comment': 'Approved - proceed with provisioning',
            }
        )
        if created:
            ApprovalRequest.objects.filter(pk=zoom.pk).update(state='provisioning')
            zoom = ApprovalRequest.objects.get(pk=zoom.pk)
            self.stdout.write(f'  Created Zoom Pro (id={zoom.id}, in provisioning - IT queue)')

        self.stdout.write(self.style.SUCCESS('  Sample data created.'))
        self.stdout.write('')
        self.stdout.write('Demo accounts (all password: password123):')
        self.stdout.write('')
        self.stdout.write('  Employees:')
        self.stdout.write('    alice@bv.com   - Employee (reports to bob)')
        self.stdout.write('    john@bv.com    - Employee (reports to bob)')
        self.stdout.write('    priya@bv.com   - Employee (reports to sarah)')
        self.stdout.write('')
        self.stdout.write('  Managers:')
        self.stdout.write('    bob@bv.com     - Manager')
        self.stdout.write('    sarah@bv.com   - Manager')
        self.stdout.write('    raj@bv.com     - Manager')
        self.stdout.write('')
        self.stdout.write('  Finance:')
        self.stdout.write('    carol@bv.com   - Finance Executive')
        self.stdout.write('    mike@bv.com    - Finance Executive')
        self.stdout.write('')
        self.stdout.write('  Finance Head:')
        self.stdout.write('    frank@bv.com   - Finance Head (Admin)')
        self.stdout.write('')
        self.stdout.write('  IT:')
        self.stdout.write('    dave@bv.com    - IT')
        self.stdout.write('')
        self.stdout.write('  Other:')
        self.stdout.write('    eve@bv.com     - Finance Executive')
        self.stdout.write('    george@bv.com  - Employee (offboard demo target)')
        self.stdout.write('    admin@bv.com   - Django Admin (superuser)')
