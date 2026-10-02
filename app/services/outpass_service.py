"""Outpass business logic service."""
import uuid
from datetime import datetime
from sqlalchemy import and_, or_
from app import db
from app.models.outpass import OutpassRequest, OutpassType, Approval
from app.models.user import Student
from app.models.notification import Notification
from app.models.audit_log import AuditLog
from app.services.qr_service import generate_qr_token
from app.services.notification_service import notify_user, notify_parent


def generate_outpass_number():
    """Generate a unique outpass number like OP-20260930-XXXX."""
    date_part = datetime.utcnow().strftime('%Y%m%d')
    uid = uuid.uuid4().hex[:6].upper()
    return f'OP-{date_part}-{uid}'


def can_apply_outpass(student):
    """Check if a student can apply for a new outpass.
    
    Returns (can_apply, reason) tuple.
    """
    # Check restriction
    if student.is_currently_restricted():
        return False, f'You are restricted from applying outpasses. Reason: {student.restriction_reason}'

    # Check for active (unreturned) outpass
    active = OutpassRequest.query.filter(
        OutpassRequest.student_id == student.id,
        OutpassRequest.status.in_(['APPROVED', 'OUT', 'OVERDUE'])
    ).first()
    if active:
        return False, 'You have an active outpass that has not been returned yet.'

    # Check for pending request
    pending = OutpassRequest.query.filter(
        OutpassRequest.student_id == student.id,
        OutpassRequest.status.in_(['PENDING', 'PARTIALLY_APPROVED'])
    ).first()
    if pending:
        return False, 'You already have a pending outpass request.'

    return True, ''


def check_monthly_limit(student, outpass_type):
    """Check if student has exceeded monthly limit for this type.
    
    Returns (within_limit, current_count, max_limit).
    """
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    count = OutpassRequest.query.filter(
        OutpassRequest.student_id == student.id,
        OutpassRequest.type_id == outpass_type.id,
        OutpassRequest.status.notin_(['CANCELLED', 'REJECTED']),
        OutpassRequest.created_at >= month_start
    ).count()
    
    return count < outpass_type.monthly_limit, count, outpass_type.monthly_limit


def check_overlap(student, out_dt, return_dt):
    """Check for overlapping outpass requests.
    
    Returns True if overlap exists.
    """
    overlap = OutpassRequest.query.filter(
        OutpassRequest.student_id == student.id,
        OutpassRequest.status.notin_(['CANCELLED', 'REJECTED', 'RETURNED', 'EXPIRED']),
        or_(
            and_(OutpassRequest.out_datetime <= out_dt, OutpassRequest.expected_return_datetime > out_dt),
            and_(OutpassRequest.out_datetime < return_dt, OutpassRequest.expected_return_datetime >= return_dt),
            and_(OutpassRequest.out_datetime >= out_dt, OutpassRequest.expected_return_datetime <= return_dt)
        )
    ).first()
    return overlap is not None


def create_outpass_request(student, form_data, attachment_filename=None):
    """Create a new outpass request and set up approval chain.
    
    Returns (outpass, error) tuple.
    """
    outpass_type = db.session.get(OutpassType, form_data['type_id'])
    if not outpass_type:
        return None, 'Invalid outpass type.'

    # Parse dates
    try:
        out_dt = datetime.strptime(form_data['out_datetime'], '%Y-%m-%dT%H:%M')
        return_dt = datetime.strptime(form_data['expected_return_datetime'], '%Y-%m-%dT%H:%M')
    except (ValueError, KeyError):
        return None, 'Invalid date format.'

    # Check monthly limit
    within_limit, count, limit = check_monthly_limit(student, outpass_type)
    if not within_limit:
        return None, f'Monthly limit reached ({count}/{limit}) for {outpass_type.name}.'

    # Check overlap
    if check_overlap(student, out_dt, return_dt):
        return None, 'You have an overlapping outpass request for these dates.'

    # Create outpass
    outpass = OutpassRequest(
        outpass_number=generate_outpass_number(),
        student_id=student.id,
        type_id=outpass_type.id,
        reason=form_data['reason'].strip(),
        destination=form_data['destination'].strip(),
        out_datetime=out_dt,
        expected_return_datetime=return_dt,
        contact_number=form_data['contact_number'].strip(),
        attachment_filename=attachment_filename,
        is_emergency=(outpass_type.code == 'EMERGENCY'),
        status='PENDING',
        current_approval_level=0
    )
    db.session.add(outpass)
    db.session.flush()  # Get the ID

    # Set up approval chain
    chain = outpass_type.get_approval_chain()
    for i, role in enumerate(chain, start=1):
        approval = Approval(
            outpass_id=outpass.id,
            level=i,
            approver_role=role,
            status='PENDING'
        )
        db.session.add(approval)

    # Parent confirmation if required
    if outpass_type.requires_parent_confirmation and student.parent_phone:
        token = uuid.uuid4().hex
        outpass.parent_confirmation_token = token
        notify_parent(student, outpass, token)

    db.session.commit()

    # Notify first approver(s)
    if chain:
        _notify_approvers(outpass, chain[0], student)

    return outpass, None


def _notify_approvers(outpass, role, student):
    """Send notifications to approvers of the given role."""
    from app.models.user import User, Staff
    
    if role == 'warden' and student.hostel_block_id:
        # Find the warden for this block
        from app.models.user import HostelBlock
        block = db.session.get(HostelBlock, student.hostel_block_id)
        if block and block.warden_id:
            notify_user(
                block.warden_id,
                f'New Outpass Request - {outpass.outpass_number}',
                f'{student.user.full_name} ({student.register_number}) has requested a {outpass.outpass_type.name} outpass.',
                category='warning',
                link=f'/warden/approve/{outpass.id}'
            )
    elif role == 'advisor':
        # Find advisors in the student's department
        advisors = User.query.filter_by(role='advisor', is_active=True).all()
        for adv in advisors:
            if adv.staff_profile and adv.staff_profile.department_id == student.department_id:
                notify_user(
                    adv.id,
                    f'New Outpass Request - {outpass.outpass_number}',
                    f'{student.user.full_name} ({student.register_number}) has requested a {outpass.outpass_type.name} outpass.',
                    category='warning',
                    link=f'/warden/approve/{outpass.id}'
                )


def process_approval(outpass, approver, action, remarks=''):
    """Process an approval/rejection action.
    
    Returns (success, message).
    """
    # Find the current pending approval for this approver's role
    current_approval = Approval.query.filter_by(
        outpass_id=outpass.id,
        approver_role=approver.role,
        status='PENDING'
    ).first()

    if not current_approval:
        return False, 'No pending approval found for your role.'

    # Check if previous levels are approved
    prev_approvals = Approval.query.filter(
        Approval.outpass_id == outpass.id,
        Approval.level < current_approval.level
    ).all()
    for pa in prev_approvals:
        if pa.status != 'APPROVED':
            return False, 'Previous approval levels must be completed first.'

    current_approval.approver_id = approver.id
    current_approval.status = action.upper()  # APPROVED or REJECTED
    current_approval.remarks = remarks
    current_approval.acted_at = datetime.utcnow()

    if action.upper() == 'REJECTED':
        if not remarks:
            return False, 'Remarks are mandatory when rejecting.'
        outpass.status = 'REJECTED'
        notify_user(
            outpass.student.user_id,
            f'Outpass Rejected - {outpass.outpass_number}',
            f'Your outpass request has been rejected. Reason: {remarks}',
            category='danger',
            link='/student/my-outpasses'
        )
    elif action.upper() == 'APPROVED':
        # Check if there are more levels
        next_approval = Approval.query.filter(
            Approval.outpass_id == outpass.id,
            Approval.level > current_approval.level,
            Approval.status == 'PENDING'
        ).first()

        if next_approval:
            outpass.status = 'PARTIALLY_APPROVED'
            outpass.current_approval_level = current_approval.level
            # Notify next approver
            student = outpass.student
            _notify_approvers(outpass, next_approval.approver_role, student)
        else:
            # All levels approved
            outpass.status = 'APPROVED'
            outpass.current_approval_level = current_approval.level
            # Generate QR token
            outpass.qr_token = generate_qr_token(outpass)
            notify_user(
                outpass.student.user_id,
                f'Outpass Approved - {outpass.outpass_number}',
                f'Your {outpass.outpass_type.name} outpass has been approved! You can now download your pass.',
                category='success',
                link='/student/my-outpasses'
            )

    db.session.commit()
    return True, f'Outpass {action.lower()}d successfully.'


def cancel_outpass(outpass, user_id):
    """Cancel a pending outpass request."""
    if outpass.status not in ('PENDING', 'PARTIALLY_APPROVED'):
        return False, 'Only pending requests can be cancelled.'
    if outpass.student.user_id != user_id:
        return False, 'You can only cancel your own requests.'
    
    outpass.status = 'CANCELLED'
    db.session.commit()
    return True, 'Outpass request cancelled.'


def expire_old_requests():
    """Auto-expire requests not approved before exit time."""
    now = datetime.utcnow()
    expired = OutpassRequest.query.filter(
        OutpassRequest.status.in_(['PENDING', 'PARTIALLY_APPROVED']),
        OutpassRequest.out_datetime < now
    ).all()
    
    count = 0
    for op in expired:
        op.status = 'EXPIRED'
        notify_user(
            op.student.user_id,
            f'Outpass Expired - {op.outpass_number}',
            'Your outpass request has expired as it was not approved before the departure time.',
            category='warning'
        )
        count += 1
    
    db.session.commit()
    return count


def check_overdue_students():
    """Find and flag overdue students (out past expected return time)."""
    now = datetime.utcnow()
    overdue = OutpassRequest.query.filter(
        OutpassRequest.status == 'OUT',
        OutpassRequest.expected_return_datetime < now,
        OutpassRequest.is_overdue == False
    ).all()

    count = 0
    for op in overdue:
        op.is_overdue = True
        op.status = 'OVERDUE'
        # Notify student
        notify_user(
            op.student.user_id,
            'OVERDUE: Please return immediately',
            f'Your outpass {op.outpass_number} has exceeded the return time. Please return to hostel immediately.',
            category='danger'
        )
        # Notify warden
        if op.student.hostel_block and op.student.hostel_block.warden_id:
            notify_user(
                op.student.hostel_block.warden_id,
                f'Student OVERDUE - {op.student.register_number}',
                f'{op.student.user.full_name} has not returned. Expected: {op.expected_return_datetime.strftime("%d-%m-%Y %H:%M")}.',
                category='danger'
            )
        count += 1

    db.session.commit()
    return count
