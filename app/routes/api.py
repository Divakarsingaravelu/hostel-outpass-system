"""REST API v1 — JSON endpoints for mobile app integration."""
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import login_user, current_user, login_required
from app import db
from app.models.user import User, Student
from app.models.outpass import OutpassRequest, OutpassType, Approval
from app.models.gate_log import GateLog
from app.services.outpass_service import create_outpass_request, can_apply_outpass, process_approval
from app.services.qr_service import verify_qr_token
from app.services.audit_service import log_action

api_bp = Blueprint('api', __name__)


def api_error(message, status_code=400):
    """Return a consistent JSON error response."""
    return jsonify({'success': False, 'error': message}), status_code


def api_success(data=None, message='OK'):
    """Return a consistent JSON success response."""
    resp = {'success': True, 'message': message}
    if data:
        resp['data'] = data
    return jsonify(resp)


# ─── Auth ────────────────────────────────────────────────────────────────────

@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    """Login and return user info."""
    data = request.get_json() or {}
    username = data.get('username', '')
    password = data.get('password', '')

    user = User.query.filter(
        (User.username == username) | (User.email == username)
    ).first()

    if not user or not user.check_password(password):
        return api_error('Invalid credentials', 401)
    if user.is_locked():
        return api_error('Account locked', 403)
    if not user.is_active:
        return api_error('Account deactivated', 403)

    user.record_successful_login()
    login_user(user)

    return api_success({
        'user_id': user.id,
        'username': user.username,
        'role': user.role,
        'full_name': user.full_name,
        'must_change_password': user.must_change_password
    })


# ─── Outpass CRUD ────────────────────────────────────────────────────────────

@api_bp.route('/outpasses', methods=['GET'])
@login_required
def api_list_outpasses():
    """List outpasses (filtered by role)."""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')

    if current_user.role == 'student':
        student = current_user.student_profile
        if not student:
            return api_error('Student profile not found')
        query = OutpassRequest.query.filter_by(student_id=student.id)
    else:
        query = OutpassRequest.query

    if status:
        query = query.filter_by(status=status)

    outpasses = query.order_by(OutpassRequest.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    return api_success({
        'outpasses': [{
            'id': op.id,
            'outpass_number': op.outpass_number,
            'type': op.outpass_type.name,
            'status': op.status,
            'destination': op.destination,
            'out_datetime': op.out_datetime.isoformat(),
            'return_datetime': op.expected_return_datetime.isoformat(),
            'created_at': op.created_at.isoformat(),
        } for op in outpasses.items],
        'total': outpasses.total,
        'pages': outpasses.pages,
        'current_page': outpasses.page
    })


@api_bp.route('/outpasses', methods=['POST'])
@login_required
def api_create_outpass():
    """Create a new outpass request."""
    if current_user.role != 'student':
        return api_error('Only students can create outpasses', 403)

    student = current_user.student_profile
    if not student:
        return api_error('Student profile not found')

    can_apply, reason = can_apply_outpass(student)
    if not can_apply:
        return api_error(reason)

    data = request.get_json() or {}
    required = ['type_id', 'reason', 'destination', 'out_datetime',
                'expected_return_datetime', 'contact_number']
    for field in required:
        if field not in data:
            return api_error(f'Missing required field: {field}')

    outpass, error = create_outpass_request(student, data)
    if error:
        return api_error(error)

    return api_success({
        'outpass_number': outpass.outpass_number,
        'status': outpass.status
    }, 'Outpass created successfully'), 201


@api_bp.route('/outpasses/<int:outpass_id>', methods=['GET'])
@login_required
def api_get_outpass(outpass_id):
    """Get outpass details."""
    outpass = db.session.get(OutpassRequest, outpass_id)
    if not outpass:
        return api_error('Not found', 404)

    return api_success({
        'outpass_number': outpass.outpass_number,
        'type': outpass.outpass_type.name,
        'status': outpass.status,
        'reason': outpass.reason,
        'destination': outpass.destination,
        'out_datetime': outpass.out_datetime.isoformat(),
        'return_datetime': outpass.expected_return_datetime.isoformat(),
        'actual_out': outpass.actual_out_datetime.isoformat() if outpass.actual_out_datetime else None,
        'actual_return': outpass.actual_return_datetime.isoformat() if outpass.actual_return_datetime else None,
        'qr_token': outpass.qr_token,
        'student': {
            'name': outpass.student.user.full_name,
            'register_number': outpass.student.register_number,
        },
        'approvals': [{
            'level': a.level,
            'role': a.approver_role,
            'status': a.status,
            'remarks': a.remarks,
            'acted_at': a.acted_at.isoformat() if a.acted_at else None,
        } for a in outpass.approvals.all()]
    })


# ─── Approvals ───────────────────────────────────────────────────────────────

@api_bp.route('/approvals/<int:outpass_id>', methods=['POST'])
@login_required
def api_approve(outpass_id):
    """Approve or reject an outpass."""
    if current_user.role not in ('warden', 'advisor', 'admin'):
        return api_error('Unauthorized', 403)

    outpass = db.session.get(OutpassRequest, outpass_id)
    if not outpass:
        return api_error('Not found', 404)

    data = request.get_json() or {}
    action = data.get('action', '').upper()
    remarks = data.get('remarks', '')

    if action not in ('APPROVED', 'REJECTED'):
        return api_error('Action must be APPROVED or REJECTED')

    success, msg = process_approval(outpass, current_user, action, remarks)
    if not success:
        return api_error(msg)

    return api_success(message=msg)


# ─── Gate ────────────────────────────────────────────────────────────────────

@api_bp.route('/gate/verify', methods=['POST'])
@login_required
def api_gate_verify():
    """Verify QR or outpass number."""
    data = request.get_json() or {}
    qr_data = data.get('qr_data', '')
    outpass_number = data.get('outpass_number', '')

    if qr_data:
        is_valid, result = verify_qr_token(qr_data)
        if not is_valid:
            return api_error(result)
        outpass = OutpassRequest.query.filter_by(outpass_number=result['op']).first()
    elif outpass_number:
        outpass = OutpassRequest.query.filter_by(outpass_number=outpass_number).first()
    else:
        return api_error('Provide qr_data or outpass_number')

    if not outpass:
        return api_error('Outpass not found', 404)

    student = outpass.student
    return api_success({
        'outpass_id': outpass.id,
        'outpass_number': outpass.outpass_number,
        'status': outpass.status,
        'student_name': student.user.full_name,
        'register_number': student.register_number,
        'type': outpass.outpass_type.name,
        'can_mark_out': outpass.status == 'APPROVED',
        'can_mark_in': outpass.status in ('OUT', 'OVERDUE'),
    })


@api_bp.route('/gate/mark', methods=['POST'])
@login_required
def api_gate_mark():
    """Mark OUT or IN."""
    if current_user.role != 'guard':
        return api_error('Only guards can mark gate actions', 403)

    data = request.get_json() or {}
    outpass_id = data.get('outpass_id')
    action = data.get('action', '').upper()

    if action not in ('OUT', 'IN'):
        return api_error('Action must be OUT or IN')

    outpass = db.session.get(OutpassRequest, outpass_id)
    if not outpass:
        return api_error('Outpass not found', 404)

    now = datetime.utcnow()

    if action == 'OUT':
        if outpass.status != 'APPROVED':
            return api_error('Only approved outpasses can be marked OUT')
        outpass.status = 'OUT'
        outpass.actual_out_datetime = now
    elif action == 'IN':
        if outpass.status not in ('OUT', 'OVERDUE'):
            return api_error('Only active outpasses can be marked IN')
        outpass.status = 'RETURNED'
        outpass.actual_return_datetime = now
        outpass.is_overdue = now > outpass.expected_return_datetime

    gate_log = GateLog(
        outpass_id=outpass.id,
        guard_id=current_user.id,
        action=action,
        timestamp=now,
        ip_address=request.remote_addr
    )
    db.session.add(gate_log)
    db.session.commit()

    log_action(f'GATE_{action}', 'OutpassRequest', outpass.id)
    return api_success(message=f'Student marked {action}')
