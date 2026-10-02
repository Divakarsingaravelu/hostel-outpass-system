"""Security guard routes — QR scanning, gate entry/exit."""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.user import Student
from app.models.outpass import OutpassRequest
from app.models.gate_log import GateLog
from app.utils.decorators import role_required
from app.services.qr_service import verify_qr_token
from app.services.notification_service import notify_user
from app.services.audit_service import log_action

guard_bp = Blueprint('guard', __name__)


@guard_bp.before_request
@login_required
def before_request():
    if current_user.role != 'guard':
        abort(403)
    if current_user.must_change_password:
        return redirect(url_for('auth.change_password'))


@guard_bp.route('/dashboard')
def dashboard():
    """Guard dashboard — scanner and today's log."""
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    today_logs = GateLog.query.filter(
        GateLog.timestamp >= today
    ).order_by(GateLog.timestamp.desc()).all()
    
    students_out = OutpassRequest.query.filter(
        OutpassRequest.status.in_(['OUT', 'OVERDUE'])
    ).all()

    return render_template('guard/dashboard.html',
                           today_logs=today_logs,
                           students_out=students_out)


@guard_bp.route('/verify', methods=['POST'])
def verify():
    """Verify an outpass by QR token or outpass number."""
    qr_data = request.form.get('qr_data', '').strip()
    outpass_number = request.form.get('outpass_number', '').strip()

    outpass = None
    error = None

    if qr_data:
        # Verify QR token
        is_valid, result = verify_qr_token(qr_data)
        if not is_valid:
            return render_template('guard/verify_result.html', error=result, outpass=None)
        outpass = OutpassRequest.query.filter_by(outpass_number=result['op']).first()
        if not outpass:
            return render_template('guard/verify_result.html',
                                   error='Outpass not found in system.', outpass=None)
    elif outpass_number:
        outpass = OutpassRequest.query.filter_by(outpass_number=outpass_number).first()
        if not outpass:
            return render_template('guard/verify_result.html',
                                   error='Outpass number not found.', outpass=None)
    else:
        flash('Please scan a QR code or enter an outpass number.', 'warning')
        return redirect(url_for('guard.dashboard'))

    # Determine what actions are available
    can_mark_out = outpass.status == 'APPROVED'
    can_mark_in = outpass.status in ('OUT', 'OVERDUE')
    
    # Check validity window
    now = datetime.utcnow()
    is_valid_window = outpass.out_datetime <= now if outpass.status == 'APPROVED' else True
    is_early_exit = now < outpass.out_datetime and outpass.status == 'APPROVED'
    is_late_return = now > outpass.expected_return_datetime and outpass.status in ('OUT', 'OVERDUE')

    # Check for already used
    already_used = outpass.status in ('RETURNED', 'CANCELLED', 'EXPIRED', 'REJECTED')

    student = outpass.student
    
    return render_template('guard/verify_result.html',
                           outpass=outpass,
                           student=student,
                           can_mark_out=can_mark_out,
                           can_mark_in=can_mark_in,
                           is_early_exit=is_early_exit,
                           is_late_return=is_late_return,
                           already_used=already_used,
                           error=None)


@guard_bp.route('/mark-out/<int:outpass_id>', methods=['POST'])
def mark_out(outpass_id):
    """Mark student as OUT at the gate."""
    outpass = db.session.get(OutpassRequest, outpass_id)
    if not outpass:
        flash('Outpass not found.', 'danger')
        return redirect(url_for('guard.dashboard'))

    if outpass.status != 'APPROVED':
        flash('Only approved outpasses can be marked OUT.', 'danger')
        return redirect(url_for('guard.dashboard'))

    now = datetime.utcnow()
    outpass.status = 'OUT'
    outpass.actual_out_datetime = now

    # Create gate log
    gate_log = GateLog(
        outpass_id=outpass.id,
        guard_id=current_user.id,
        action='OUT',
        timestamp=now,
        ip_address=request.remote_addr
    )
    db.session.add(gate_log)
    db.session.commit()

    log_action('GATE_OUT', 'OutpassRequest', outpass.id,
               f'Student {outpass.student.register_number} marked OUT by guard {current_user.username}')
    
    # Notify student
    notify_user(outpass.student.user_id,
                'Gate Exit Recorded',
                f'You have been marked OUT at {now.strftime("%d-%m-%Y %H:%M")}.',
                category='info')

    flash(f'Student {outpass.student.user.full_name} marked OUT successfully.', 'success')
    return redirect(url_for('guard.dashboard'))


@guard_bp.route('/mark-in/<int:outpass_id>', methods=['POST'])
def mark_in(outpass_id):
    """Mark student as IN (returned) at the gate."""
    outpass = db.session.get(OutpassRequest, outpass_id)
    if not outpass:
        flash('Outpass not found.', 'danger')
        return redirect(url_for('guard.dashboard'))

    if outpass.status not in ('OUT', 'OVERDUE'):
        flash('Only outgoing students can be marked IN.', 'danger')
        return redirect(url_for('guard.dashboard'))

    now = datetime.utcnow()
    
    # Check if late return
    is_late = now > outpass.expected_return_datetime
    
    outpass.status = 'RETURNED'
    outpass.actual_return_datetime = now
    outpass.is_overdue = is_late

    # Create gate log
    gate_log = GateLog(
        outpass_id=outpass.id,
        guard_id=current_user.id,
        action='IN',
        timestamp=now,
        remarks='Late return' if is_late else None,
        ip_address=request.remote_addr
    )
    db.session.add(gate_log)
    db.session.commit()

    log_action('GATE_IN', 'OutpassRequest', outpass.id,
               f'Student {outpass.student.register_number} marked IN. Late: {is_late}')

    notify_user(outpass.student.user_id,
                'Gate Entry Recorded',
                f'You have been marked IN at {now.strftime("%d-%m-%Y %H:%M")}.' +
                (' (Late return recorded)' if is_late else ''),
                category='warning' if is_late else 'success')

    status_msg = 'LATE RETURN recorded.' if is_late else 'Return recorded.'
    flash(f'Student {outpass.student.user.full_name} marked IN. {status_msg}', 
          'warning' if is_late else 'success')
    return redirect(url_for('guard.dashboard'))


@guard_bp.route('/movement-log')
def movement_log():
    """View today's movement log."""
    date_filter = request.args.get('date', '')
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d')
        except ValueError:
            filter_date = datetime.utcnow()
    else:
        filter_date = datetime.utcnow()
    
    day_start = filter_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = filter_date.replace(hour=23, minute=59, second=59)
    
    logs = GateLog.query.filter(
        GateLog.timestamp >= day_start,
        GateLog.timestamp <= day_end
    ).order_by(GateLog.timestamp.desc()).all()

    return render_template('guard/movement_log.html', logs=logs, date_filter=date_filter)


# JSON endpoint for QR scan (used by JS fetch)
@guard_bp.route('/api/verify-qr', methods=['POST'])
def api_verify_qr():
    """API endpoint for QR verification via JS."""
    data = request.get_json() or {}
    qr_data = data.get('qr_data', '')
    
    if not qr_data:
        return jsonify({'valid': False, 'error': 'No QR data provided'}), 400

    is_valid, result = verify_qr_token(qr_data)
    if not is_valid:
        return jsonify({'valid': False, 'error': result}), 400

    outpass = OutpassRequest.query.filter_by(outpass_number=result['op']).first()
    if not outpass:
        return jsonify({'valid': False, 'error': 'Outpass not found'}), 404

    student = outpass.student
    return jsonify({
        'valid': True,
        'outpass_id': outpass.id,
        'outpass_number': outpass.outpass_number,
        'student_name': student.user.full_name,
        'register_number': student.register_number,
        'room': student.room.room_number if student.room else 'N/A',
        'block': student.hostel_block.name if student.hostel_block else 'N/A',
        'type': outpass.outpass_type.name,
        'status': outpass.status,
        'valid_from': outpass.out_datetime.strftime('%d-%m-%Y %H:%M'),
        'valid_until': outpass.expected_return_datetime.strftime('%d-%m-%Y %H:%M'),
        'photo': student.user.photo_filename,
        'can_mark_out': outpass.status == 'APPROVED',
        'can_mark_in': outpass.status in ('OUT', 'OVERDUE'),
    })
