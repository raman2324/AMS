from approvals.models import ApprovalRequest, RequestType


def get_subscriptions_for_user(user):
    """Get all subscriptions visible to this user."""
    from accounts.models import Role
    if user.role in (Role.FINANCE, Role.ADMIN, Role.IT):
        return ApprovalRequest.objects.filter(
            request_type=RequestType.SUBSCRIPTION
        ).select_related('submitted_by').order_by('-created_at')
    return ApprovalRequest.objects.filter(
        request_type=RequestType.SUBSCRIPTION,
        submitted_by=user,
    ).order_by('-created_at')
