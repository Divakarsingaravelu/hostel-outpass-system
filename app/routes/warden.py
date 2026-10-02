"""Warden/Advisor routes — approval queue, bulk approve, block management."""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models.user import User, Student, HostelBlock
from app.models.outpass import OutpassRequest, OutpassType, Approval
from app.models.notification import Notification
from app.utils.decorators import role_required
from app.services.outpass_service import process_approval, expire_old_requests, check_overdue_students
from app.services.audit_service import log_action

warden_bp = Blueprint('warden', __name__)


@warden_bp.before_request
@login_required
def before_request():
    if current_user.role not in ('warden', 'advisor', 'admin'):
        abort(403)
    if current_user.must_change_password:
        return redirect(url_for('auth.change_password'))
    expire_old_requests()
    check_overdue_students()


@warden_bp.route('/dashboard')
def dashboard():
    """Warden/advisor dashboard."""
    # Get the warden's block
    block = None
    if current_user.staff_profile and current_user.staff_profile.hostel_block_id:
        block = db.session.get(HostelBlock, current_user.staff_profile.hostel_block_id)

    # Build query for pending requests
    query = OutpassRequest.query.filter(
        OutpassRequest.status.in_(['PENDING', 'PARTIALLY_APPROVED'])
    )
    
    # For warden: filter by their block's students
    if current_user.role == 'warden' and block:
        student_ids = [s.id for s in Student.query.filter_by(hostel_block_id=block.id).all()]
        query = query.filter(OutpassRequest.student_id.in_(student_ids))
    elif current_user.role == 'advisor' and current_user.staff_profile:
        # Advisor: filter by their department's students
        dept_id = current_user.staff_profile.department_id
        student_ids = [s.id for s in Student.query.filter_by(department_id=dept_id).all()]
        query = query.filter(OutpassRequest.student_id.in_(student_ids))

    # Separate emergency requests
    emergency_requests = query.filter(OutpassRequest.is_emergency == True).order_by(
        OutpassRequest.created_at.asc()
    ).all()
    
    regular_requests = query.filter(OutpassRequest.is_emergency == False).order_by(
        OutpassRequest.created_at.asc()
    ).all()

    # Students currently outside
    out_query = OutpassRequest.query.filter(
        OutpassRequest.status.in_(['OUT', 'OVERDUE'])
    )
    if current_user.role == 'warden' and block:
        out_query = out_query.filter(OutpassRequest.student_id.in_(student_ids))
    students_out = out_query.all()

    # Counts
    total_pending = len(emergency_requests) + len(regular_requests)
    overdue_count = OutpassRequest.query.filter(OutpassRequest.status == 'OVERDUE').count()

    return render_template('warden/dashboard.html',
                           block=block,
                           emergency_requests=emergency_requests,
                           regular_requests=regular_requests,
                           students_out=students_out,
                           total_pending=total_pending,
                           overdue_count=overdue_count)


@warden_bp.route('/approve/<int:outpass_id>', methods=['GET', 'POST'])
def approve(outpass_id):
    """View and approve/reject an outpass request."""
    outpass = db.session.get(OutpassRequest, outpass_id)
    if not outpass:
        flash('Outpass not found.', 'danger')
        return redirect(url_for('warden.dashboard'))

    if request.method == 'POST':
        action = request.form.get('action', '').upper()
        remarks = request.form.get('remarks', '').strip()

        if action not in ('APPROVED', 'REJECTED'):
            flash('Invalid action.', 'danger')
            return redirect(url_for('warden.approve', outpass_id=outpass_id))

        if action == 'REJECTED' and not remarks:
            flash('Remarks are mandatory when rejecting.', 'danger')
            return redirect(url_for('warden.approve', outpass_id=outpass_id))

        success, msg = process_approval(outpass, current_user, action, remarks)
        if success:
            log_action(f'OUTPASS_{action}', 'OutpassRequest', outpass.id,
                       f'{current_user.role} {action.lower()} outpass {outpass.outpass_number}. Remarks: {remarks}')
            flash(msg, 'success')
        else:
            flash(msg, 'danger')
        return redirect(url_for('warden.dashboard'))

    return render_template('warden/approve.html', outpass=outpass)


@warden_bp.route('/bulk-approve', methods=['POST'])
def bulk_approve():
    """Bulk approve selected outpass requests."""
    ids = request.form.getlist('outpass_ids')
    remarks = request.form.get('remarks', 'Bulk approved')
    count = 0
    
    for oid in ids:
        outpass = db.session.get(OutpassRequest, int(oid))
        if outpass:
            success, _ = process_approval(outpass, current_user, 'APPROVED', remarks)
            if success:
                log_action('OUTPASS_APPROVED', 'OutpassRequest', outpass.id,
                           f'Bulk approved by {current_user.role}')
                count += 1
    
    flash(f'Approved {count} outpass request(s).', 'success')
    return redirect(url_for('warden.dashboard'))


@warden_bp.route('/queue')
def approval_queue():
    """Full approval queue with filters."""
    status_filter = request.args.get('status', '')
    type_filter = request.args.get('type', '')
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)

    query = OutpassRequest.query

    # Filter by block for warden
    if current_user.role == 'warden' and current_user.staff_profile and current_user.staff_profile.hostel_block_id:
        student_ids = [s.id for s in Student.query.filter_by(
            hostel_block_id=current_user.staff_profile.hostel_block_id
        ).all()]
        query = query.filter(OutpassRequest.student_id.in_(student_ids))
    elif current_user.role == 'advisor' and current_user.staff_profile:
        student_ids = [s.id for s in Student.query.filter_by(
            department_id=current_user.staff_profile.department_id
        ).all()]
        query = query.filter(OutpassRequest.student_id.in_(student_ids))

    if status_filter:
        query = query.filter_by(status=status_filter)
    if type_filter:
        query = query.filter_by(type_id=int(type_filter))
    if search:
        matching_students = Student.query.filter(
            Student.register_number.ilike(f'%{search}%')
        ).all()
        matching_users = User.query.filter(
            User.full_name.ilike(f'%{search}%')
        ).all()
        student_ids_search = [s.id for s in matching_students]
        for u in matching_users:
            if u.student_profile:
                student_ids_search.append(u.student_profile.id)
        if student_ids_search:
            query = query.filter(OutpassRequest.student_id.in_(student_ids_search))
        else:
            query = query.filter(OutpassRequest.outpass_number.ilike(f'%{search}%'))

    outpasses = query.order_by(OutpassRequest.created_at.desc()).paginate(
        page=page, per_page=15, error_out=False
    )
    outpass_types = OutpassType.query.filter_by(is_active=True).all()

    return render_template('warden/queue.html',
                           outpasses=outpasses,
                           outpass_types=outpass_types,
                           status_filter=status_filter,
                           type_filter=type_filter,
                           search=search)


@warden_bp.route('/students')
def students_list():
    """View students in warden's block."""
    block = None
    students = []
    
    if current_user.staff_profile and current_user.staff_profile.hostel_block_id:
        block = db.session.get(HostelBlock, current_user.staff_profile.hostel_block_id)
        students = Student.query.filter_by(hostel_block_id=block.id).all()
    else:
        students = Student.query.all()

    return render_template('warden/students.html', block=block, students=students)


@warden_bp.route('/notifications')
def notifications():
    """View warden notifications."""
    page = request.args.get('page', 1, type=int)
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    return render_template('warden/notifications.html', notifications=notifs)


@warden_bp.route('/notifications/mark-read', methods=['POST'])
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return redirect(url_for('warden.notifications'))
