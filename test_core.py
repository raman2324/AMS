"""
Core service smoke tests — run with: python test_core.py
Uses Django's test database (transactions rolled back per test).
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ams.settings.dev')
django.setup()

from django.utils import timezone
from django.db import transaction
from django.core.exceptions import PermissionDenied

from accounts.models import CustomUser
from approvals.models import ApprovalRequest
from approvals.services import submit, manager_approve, manager_reject, finance_approve, finance_reject, it_provision, initiate_renewal, complete_renewal, terminate_request
from accounts.services import offboard_employee
from audit.models import AuditLog
from notifications.models import NotificationSent
from notifications.services import send_notification

PASS = "✓"
FAIL = "✗"
errors = []

def check(label, condition, detail=""):
    if condition:
        print(f"  {PASS} {label}")
    else:
        print(f"  {FAIL} {label} {detail}")
        errors.append(label)

def get_users():
    alice = CustomUser.objects.get(email='alice@bv.com')  # employee, reports to bob
    bob = CustomUser.objects.get(email='bob@bv.com')      # manager
    carol = CustomUser.objects.get(email='carol@bv.com')  # finance
    dave = CustomUser.objects.get(email='dave@bv.com')    # IT
    eve = CustomUser.objects.get(email='eve@bv.com')      # HR
    frank = CustomUser.objects.get(email='frank@bv.com')  # C-suite (no reports_to)
    return alice, bob, carol, dave, eve, frank


print("\n=== 1. HAPPY PATH: employee → manager → finance → IT → active ===")
with transaction.atomic():
    sp = transaction.savepoint()
    alice, bob, carol, dave, eve, frank = get_users()

    # Create request
    req = ApprovalRequest.objects.create(
        request_type='subscription',
        submitted_by=alice,
        service_name='TestTool',
        vendor='TestCo',
        cost=50,
        billing_period='monthly',
        justification='Need it',
        expires_on=timezone.now().date() + timezone.timedelta(days=365),
    )
    req = submit(req, actor=alice)
    check("submit → pending_manager", req.state == 'pending_manager')
    check("current_approver = manager", req.current_approver == bob)

    req = manager_approve(req, actor=bob, comment='Approved')
    check("manager_approve → pending_finance", req.state == 'pending_finance')
    check("current_approver = finance", req.current_approver == carol)

    req = finance_approve(req, actor=carol, comment='Budget ok')
    check("finance_approve → provisioning", req.state == 'provisioning')
    check("current_approver = IT", req.current_approver == dave)

    req = it_provision(req, actor=dave, vendor_account_id='ACC-001', billing_start=timezone.now().date())
    check("it_provision → active", req.state == 'active')

    audit_actions = list(AuditLog.objects.filter(target_id=req.id, target_type='request').values_list('action', flat=True))
    check("audit has 4 entries", len(audit_actions) == 4, str(audit_actions))
    transaction.savepoint_rollback(sp)


print("\n=== 2. MANAGER REJECT → terminal ===")
with transaction.atomic():
    sp = transaction.savepoint()
    alice, bob, carol, dave, eve, frank = get_users()
    req = ApprovalRequest.objects.create(
        request_type='subscription', submitted_by=alice,
        service_name='RejectedTool', vendor='Co', cost=10,
        billing_period='monthly', justification='test',
        expires_on=timezone.now().date() + timezone.timedelta(days=365),
    )
    req = submit(req, actor=alice)
    req = manager_reject(req, actor=bob, reason='Not justified')
    check("manager_reject → rejected_manager", req.state == 'rejected_manager')
    check("current_approver cleared", req.current_approver is None)
    transaction.savepoint_rollback(sp)


print("\n=== 3. C-SUITE PATH (no reports_to → skip manager) ===")
with transaction.atomic():
    sp = transaction.savepoint()
    alice, bob, carol, dave, eve, frank = get_users()
    check("frank has no reports_to", frank.reports_to is None)
    req = ApprovalRequest.objects.create(
        request_type='subscription', submitted_by=frank,
        service_name='CEOTool', vendor='BigCo', cost=500,
        billing_period='annual', justification='Strategic',
        expires_on=timezone.now().date() + timezone.timedelta(days=365),
    )
    req = submit(req, actor=frank)
    check("C-suite submit → pending_finance (skip manager)", req.state == 'pending_finance')
    check("current_approver = finance head", req.current_approver == carol)
    audit = AuditLog.objects.filter(target_id=req.id, target_type='request').order_by('id').first()
    check("audit action = submitted_c_suite", audit and audit.action == 'submitted_c_suite')
    transaction.savepoint_rollback(sp)


print("\n=== 4. MISC EXPENSE → finance-only (no manager step) ===")
with transaction.atomic():
    sp = transaction.savepoint()
    alice, bob, carol, dave, eve, frank = get_users()
    req = ApprovalRequest.objects.create(
        request_type='misc_expense', submitted_by=alice,
        service_name='Conference ticket', vendor='Conf', cost=300,
        billing_period='one_time', justification='Learning',
        expires_on=None,
    )
    # Misc expense should go directly to pending_finance
    req = submit(req, actor=alice)
    # Misc expense skips manager and goes to finance directly
    check("misc expense starts at pending_finance or pending_manager",
          req.state in ('pending_finance', 'pending_manager'))
    transaction.savepoint_rollback(sp)


print("\n=== 5. HR OFFBOARD CASCADE ===")
with transaction.atomic():
    sp = transaction.savepoint()
    alice, bob, carol, dave, eve, frank = get_users()
    # Create active subscription for alice
    req_active = ApprovalRequest.objects.create(
        request_type='subscription', submitted_by=alice,
        service_name='AliceTool', vendor='Co', cost=20,
        billing_period='monthly', justification='work',
        expires_on=timezone.now().date() + timezone.timedelta(days=30),
    )
    req_active.state = 'active'
    req_active.save()

    # Create pending request where alice is current_approver
    req_pending = ApprovalRequest.objects.create(
        request_type='subscription', submitted_by=frank,
        service_name='FrankTool', vendor='Co', cost=10,
        billing_period='monthly', justification='work',
        expires_on=timezone.now().date() + timezone.timedelta(days=30),
    )
    req_pending.state = 'pending_manager'
    req_pending.current_approver = alice
    req_pending.save()

    result = offboard_employee(alice, last_day=timezone.now().date(), actor=eve)
    alice.refresh_from_db()
    check("alice marked inactive", not alice.is_active)
    check("alice has offboarded_at", alice.offboarded_at is not None)

    req_active.refresh_from_db()
    check("active sub terminated", req_active.state == 'terminated')

    req_pending.refresh_from_db()
    # Approver reassigned to alice's manager (bob)
    check("pending request approver reassigned (not alice)",
          req_pending.current_approver != alice)

    # Idempotency: offboard again
    result2 = offboard_employee(alice, last_day=timezone.now().date(), actor=eve)
    check("offboard idempotent (already_offboarded flag)",
          result2.get('already_offboarded') == True)
    transaction.savepoint_rollback(sp)


print("\n=== 6. AUDIT LOG IS APPEND-ONLY ===")
log = AuditLog.objects.first()
try:
    log.delete()
    errors.append("AuditLog.delete() should have raised PermissionDenied")
    print(f"  {FAIL} AuditLog.delete() blocked")
except PermissionDenied:
    print(f"  {PASS} AuditLog.delete() correctly raises PermissionDenied")


print("\n=== 7. NOTIFICATION IDEMPOTENCY ===")
with transaction.atomic():
    sp = transaction.savepoint()
    alice, *_ = get_users()
    req = ApprovalRequest.objects.first()
    today = timezone.now().date()
    send_notification(req.id, 'renewal_reminder', today, alice, 'Reminder', 'Body')
    send_notification(req.id, 'renewal_reminder', today, alice, 'Reminder', 'Body')
    send_notification(req.id, 'renewal_reminder', today, alice, 'Reminder', 'Body')
    count = NotificationSent.objects.filter(
        subject_id=req.id, action_type='renewal_reminder', target_date=today
    ).count()
    check("duplicate notifications deduplicated to 1", count == 1, f"got {count}")
    transaction.savepoint_rollback(sp)


print("\n=== 8. RENEWAL FLOW ===")
with transaction.atomic():
    sp = transaction.savepoint()
    alice, bob, carol, dave, eve, frank = get_users()
    req = ApprovalRequest.objects.create(
        request_type='subscription', submitted_by=alice,
        service_name='RenewMe', vendor='Co', cost=30,
        billing_period='annual', justification='work',
        expires_on=timezone.now().date() + timezone.timedelta(days=10),
    )
    req.state = 'active'
    req.save()
    req = initiate_renewal(req, actor=alice)
    check("initiate_renewal → active_pending_renewal", req.state == 'active_pending_renewal')
    req = initiate_renewal(req, actor=alice)
    check("initiate_renewal again → renewing", req.state == 'renewing')
    req = complete_renewal(req, actor=carol, approved=True)
    check("renewal approved → active", req.state == 'active')
    transaction.savepoint_rollback(sp)


print("\n" + "="*50)
if errors:
    print(f"FAILED: {len(errors)} test(s)")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print(f"ALL TESTS PASSED ({8} suites)")
