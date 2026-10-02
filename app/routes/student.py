"""Student routes — dashboard, profile, outpass application, history."""
import os
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, current_app, send_file, abort)
from flask_login import login_required, current_user
from app import db
from app.models.user import Student
from app.models.outpass import OutpassRequest, OutpassType
from app.models.notification import Notification
from app.utils.decorators import role_required
from app.utils.validators import validate_outpass_form, validate_file_upload
from app.services.outpass_service import (
    can_apply_outpass, create_outpass_request, cancel_outpass,
    check_monthly_limit, expire_old_requests, check_overdue_students
)
from app.services.pdf_service import generate_outpass_pdf
from app.services.qr_service import generate_qr_image
from app.services.audit_service import log_action

student_bp = Blueprint('student', __name__)


@student_bp.before_request
@login_required
def before_request():
    """Ensure only students access these routes."""
    if current_user.role != 'student':
        abort(403)
    if current_user.must_change_password:
        return redirect(url_for('auth.change_password'))
    # Run background checks
    expire_old_requests()
    check_overdue_students()


@student_bp.route('/dashboard')
def dashboard():
    """Student dashboard with status overview."""
    student = current_user.student_profile
    if not student:
        flash('Student profile not found. Contact admin.', 'danger')
        return redirect(url_for('auth.logout'))

    # Current status
    active_outpass = OutpassRequest.query.filter(
        OutpassRequest.student_id == student.id,
        OutpassRequest.status.in_(['APPROVED', 'OUT', 'OVERDUE'])
    ).first()

    is_outside = active_outpass and active_outpass.status in ('OUT', 'OVERDUE')

    # Counts
    pending_count = OutpassRequest.query.filter_by(
        student_id=student.id, status='PENDING'
    ).count() + OutpassRequest.query.filter_by(
        student_id=student.id, status='PARTIALLY_APPROVED'
    ).count()

    # Monthly counts per type
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_count = OutpassRequest.query.filter(
        OutpassRequest.student_id == student.id,
        OutpassRequest.status.notin_(['CANCELLED', 'REJECTED']),
        OutpassRequest.created_at >= month_start
    ).count()

    # Recent history
    recent = OutpassRequest.query.filter_by(student_id=student.id).order_by(
        OutpassRequest.created_at.desc()
    ).limit(10).all()

    # Notifications
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).limit(10).all()

    return render_template('student/dashboard.html',
                           student=student,
                           active_outpass=active_outpass,
                           is_outside=is_outside,
                           pending_count=pending_count,
                           monthly_count=monthly_count,
                           recent=recent,
                           notifications=notifications)


@student_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    """View and edit student profile."""
    student = current_user.student_profile
    if not student:
        flash('Student profile not found.', 'danger')
        return redirect(url_for('student.dashboard'))

    if request.method == 'POST':
        # Update profile fields
        current_user.phone = request.form.get('phone', current_user.phone)
        student.parent_name = request.form.get('parent_name', student.parent_name)
        student.parent_phone = request.form.get('parent_phone', student.parent_phone)
        student.parent_email = request.form.get('parent_email', student.parent_email)
        student.blood_group = request.form.get('blood_group', student.blood_group)
        student.address = request.form.get('address', student.address)

        # Photo upload
        if 'photo' in request.files:
            photo = request.files['photo']
            is_valid, error, safe_name = validate_file_upload(photo)
            if not is_valid:
                flash(error, 'danger')
                return render_template('student/profile.html', student=student)
            if safe_name:
                upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'photos')
                os.makedirs(upload_dir, exist_ok=True)
                photo.save(os.path.join(upload_dir, safe_name))
                current_user.photo_filename = safe_name

        db.session.commit()
        log_action('PROFILE_UPDATED', 'Student', student.id)
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('student.profile'))

    return render_template('student/profile.html', student=student)


@student_bp.route('/apply', methods=['GET', 'POST'])
def apply_outpass():
    """Apply for a new outpass."""
    student = current_user.student_profile
    if not student:
        flash('Student profile not found.', 'danger')
        return redirect(url_for('student.dashboard'))

    # Check if can apply
    can_apply, reason = can_apply_outpass(student)
    if not can_apply:
        flash(reason, 'warning')
        return redirect(url_for('student.dashboard'))

    outpass_types = OutpassType.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        # Validate form
        is_valid, errors = validate_outpass_form(request.form, student)
        if not is_valid:
            for err in errors:
                flash(err, 'danger')
            return render_template('student/apply.html', outpass_types=outpass_types)

        # Handle attachment
        attachment_filename = None
        if 'attachment' in request.files:
            file = request.files['attachment']
            valid, error, safe_name = validate_file_upload(file)
            if not valid:
                flash(error, 'danger')
                return render_template('student/apply.html', outpass_types=outpass_types)
            if safe_name:
                upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'attachments')
                os.makedirs(upload_dir, exist_ok=True)
                file.save(os.path.join(upload_dir, safe_name))
                attachment_filename = safe_name

        # Create outpass
        form_data = {
            'type_id': int(request.form.get('type_id')),
            'reason': request.form.get('reason', ''),
            'destination': request.form.get('destination', ''),
            'out_datetime': request.form.get('out_datetime', ''),
            'expected_return_datetime': request.form.get('expected_return_datetime', ''),
            'contact_number': request.form.get('contact_number', ''),
        }

        outpass, error = create_outpass_request(student, form_data, attachment_filename)
        if error:
            flash(error, 'danger')
            return render_template('student/apply.html', outpass_types=outpass_types)

        log_action('OUTPASS_CREATED', 'OutpassRequest', outpass.id,
                   f'Outpass {outpass.outpass_number} created')
        flash(f'Outpass request {outpass.outpass_number} submitted successfully!', 'success')
        return redirect(url_for('student.my_outpasses'))

    return render_template('student/apply.html', outpass_types=outpass_types)


@student_bp.route('/my-outpasses')
def my_outpasses():
    """View all outpass requests with filters."""
    student = current_user.student_profile
    if not student:
        return redirect(url_for('student.dashboard'))

    # Filters
    status_filter = request.args.get('status', '')
    type_filter = request.args.get('type', '')
    page = request.args.get('page', 1, type=int)

    query = OutpassRequest.query.filter_by(student_id=student.id)
    if status_filter:
        query = query.filter_by(status=status_filter)
    if type_filter:
        query = query.filter_by(type_id=int(type_filter))

    outpasses = query.order_by(OutpassRequest.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    outpass_types = OutpassType.query.filter_by(is_active=True).all()

    return render_template('student/my_outpasses.html',
                           outpasses=outpasses,
                           outpass_types=outpass_types,
                           status_filter=status_filter,
                           type_filter=type_filter)


@student_bp.route('/cancel/<int:outpass_id>', methods=['POST'])
def cancel(outpass_id):
    """Cancel a pending outpass request."""
    outpass = db.session.get(OutpassRequest, outpass_id)
    if not outpass:
        flash('Outpass not found.', 'danger')
        return redirect(url_for('student.my_outpasses'))

    success, msg = cancel_outpass(outpass, current_user.id)
    if success:
        log_action('OUTPASS_CANCELLED', 'OutpassRequest', outpass.id)
        flash(msg, 'success')
    else:
        flash(msg, 'danger')
    return redirect(url_for('student.my_outpasses'))


@student_bp.route('/download/<int:outpass_id>')
def download_pdf(outpass_id):
    """Download outpass as PDF."""
    outpass = db.session.get(OutpassRequest, outpass_id)
    if not outpass or outpass.student.user_id != current_user.id:
        abort(403)
    if outpass.status not in ('APPROVED', 'OUT', 'RETURNED'):
        flash('PDF only available for approved outpasses.', 'warning')
        return redirect(url_for('student.my_outpasses'))

    # Generate QR image if not exists
    if outpass.qr_token and not outpass.qr_filename:
        outpass.qr_filename = generate_qr_image(outpass.qr_token, outpass.outpass_number)
        db.session.commit()

    pdf_buf = generate_outpass_pdf(outpass)
    return send_file(
        pdf_buf,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'outpass_{outpass.outpass_number}.pdf'
    )


@student_bp.route('/view/<int:outpass_id>')
def view_outpass(outpass_id):
    """View outpass details with timeline."""
    outpass = db.session.get(OutpassRequest, outpass_id)
    if not outpass or outpass.student.user_id != current_user.id:
        abort(403)
    return render_template('student/view_outpass.html', outpass=outpass)


@student_bp.route('/notifications')
def notifications():
    """View all notifications."""
    page = request.args.get('page', 1, type=int)
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    return render_template('student/notifications.html', notifications=notifs)


@student_bp.route('/notifications/mark-read', methods=['POST'])
def mark_notifications_read():
    """Mark all notifications as read."""
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return redirect(url_for('student.notifications'))
