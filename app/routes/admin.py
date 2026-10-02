"""Admin routes — user CRUD, system config, reports, audit logs."""
import csv
import io
from datetime import datetime, timedelta
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, abort, send_file, jsonify)
from flask_login import login_required, current_user
from app import db
from app.models.user import User, Student, Staff, Department, HostelBlock, Room
from app.models.outpass import OutpassRequest, OutpassType, Approval
from app.models.gate_log import GateLog
from app.models.notification import Notification
from app.models.announcement import Announcement
from app.models.audit_log import AuditLog
from app.models.setting import Setting
from app.utils.decorators import role_required
from app.services.audit_service import log_action

admin_bp = Blueprint('admin', __name__)


@admin_bp.before_request
@login_required
def before_request():
    if current_user.role != 'admin':
        abort(403)
    if current_user.must_change_password:
        return redirect(url_for('auth.change_password'))


@admin_bp.route('/dashboard')
def dashboard():
    """Admin dashboard with system overview."""
    total_students = Student.query.count()
    total_staff = Staff.query.count()
    total_outpasses = OutpassRequest.query.count()
    students_out = OutpassRequest.query.filter(OutpassRequest.status.in_(['OUT', 'OVERDUE'])).count()
    overdue = OutpassRequest.query.filter_by(status='OVERDUE').count()
    pending = OutpassRequest.query.filter(OutpassRequest.status.in_(['PENDING', 'PARTIALLY_APPROVED'])).count()

    # Today's stats
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_exits = GateLog.query.filter(GateLog.timestamp >= today, GateLog.action == 'OUT').count()
    today_entries = GateLog.query.filter(GateLog.timestamp >= today, GateLog.action == 'IN').count()

    # Recent activity
    recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()
    recent_outpasses = OutpassRequest.query.order_by(OutpassRequest.created_at.desc()).limit(10).all()

    return render_template('admin/dashboard.html',
                           total_students=total_students,
                           total_staff=total_staff,
                           total_outpasses=total_outpasses,
                           students_out=students_out,
                           overdue=overdue,
                           pending=pending,
                           today_exits=today_exits,
                           today_entries=today_entries,
                           recent_logs=recent_logs,
                           recent_outpasses=recent_outpasses)


# ─── User Management ─────────────────────────────────────────────────────────

@admin_bp.route('/users')
def users():
    """List all users."""
    role_filter = request.args.get('role', '')
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)

    query = User.query
    if role_filter:
        query = query.filter_by(role=role_filter)
    if search:
        query = query.filter(
            (User.username.ilike(f'%{search}%')) |
            (User.full_name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )

    users_page = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template('admin/users.html', users=users_page,
                           role_filter=role_filter, search=search)


@admin_bp.route('/users/create', methods=['GET', 'POST'])
def create_user():
    """Create a new user."""
    departments = Department.query.all()
    blocks = HostelBlock.query.all()
    rooms = Room.query.all()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip() or None
        role = request.form.get('role', 'student')
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', 'Changeme@123')

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return render_template('admin/create_user.html',
                                   departments=departments, blocks=blocks, rooms=rooms)

        user = User(
            username=username, email=email, role=role,
            full_name=full_name, phone=phone,
            must_change_password=True
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        if role == 'student':
            student = Student(
                user_id=user.id,
                register_number=username,
                department_id=int(request.form.get('department_id')) if request.form.get('department_id') else None,
                year=int(request.form.get('year', 1)),
                hostel_block_id=int(request.form.get('block_id')) if request.form.get('block_id') else None,
                room_id=int(request.form.get('room_id')) if request.form.get('room_id') else None,
                parent_name=request.form.get('parent_name', ''),
                parent_phone=request.form.get('parent_phone', ''),
                blood_group=request.form.get('blood_group', ''),
            )
            db.session.add(student)
        else:
            staff = Staff(
                user_id=user.id,
                staff_id=username,
                department_id=int(request.form.get('department_id')) if request.form.get('department_id') else None,
                designation=request.form.get('designation', ''),
                hostel_block_id=int(request.form.get('block_id')) if request.form.get('block_id') else None,
            )
            db.session.add(staff)

        db.session.commit()
        log_action('USER_CREATED', 'User', user.id, f'Created {role} user: {username}')
        flash(f'User {username} created successfully.', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/create_user.html',
                           departments=departments, blocks=blocks, rooms=rooms)


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
def toggle_user(user_id):
    """Activate/deactivate a user."""
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin.users'))
    user.is_active = not user.is_active
    db.session.commit()
    log_action('USER_TOGGLED', 'User', user.id,
               f'User {user.username} {"activated" if user.is_active else "deactivated"}')
    flash(f'User {user.username} {"activated" if user.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/import', methods=['GET', 'POST'])
def import_users():
    """Bulk import students from CSV."""
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file uploaded.', 'danger')
            return redirect(url_for('admin.import_users'))

        file = request.files['csv_file']
        if not file.filename.endswith('.csv'):
            flash('Only CSV files are accepted.', 'danger')
            return redirect(url_for('admin.import_users'))

        try:
            stream = io.StringIO(file.stream.read().decode('utf-8'))
            reader = csv.DictReader(stream)
            count = 0
            errors = []

            for row in reader:
                username = row.get('register_number', '').strip()
                if not username:
                    continue
                if User.query.filter_by(username=username).first():
                    errors.append(f'Skipped {username}: already exists')
                    continue

                user = User(
                    username=username,
                    email=row.get('email', '').strip() or None,
                    role='student',
                    full_name=row.get('full_name', username),
                    phone=row.get('phone', ''),
                    must_change_password=True
                )
                user.set_password(row.get('password', 'Student@123'))
                db.session.add(user)
                db.session.flush()

                dept = Department.query.filter_by(code=row.get('department', '')).first()
                block = HostelBlock.query.filter_by(code=row.get('block', '')).first()
                room = None
                if block and row.get('room'):
                    room = Room.query.filter_by(room_number=row.get('room'), block_id=block.id).first()

                student = Student(
                    user_id=user.id,
                    register_number=username,
                    department_id=dept.id if dept else None,
                    year=int(row.get('year', 1)),
                    hostel_block_id=block.id if block else None,
                    room_id=room.id if room else None,
                    parent_name=row.get('parent_name', ''),
                    parent_phone=row.get('parent_phone', ''),
                    blood_group=row.get('blood_group', ''),
                )
                db.session.add(student)
                count += 1

            db.session.commit()
            log_action('BULK_IMPORT', 'User', None, f'Imported {count} students')
            flash(f'Successfully imported {count} students.', 'success')
            if errors:
                for e in errors[:5]:
                    flash(e, 'warning')
        except Exception as e:
            db.session.rollback()
            flash(f'Import failed: {str(e)}', 'danger')

        return redirect(url_for('admin.users'))

    return render_template('admin/import_users.html')


# ─── Hostel Block & Room Management ──────────────────────────────────────────

@admin_bp.route('/blocks')
def blocks():
    """Manage hostel blocks."""
    all_blocks = HostelBlock.query.all()
    return render_template('admin/blocks.html', blocks=all_blocks)


@admin_bp.route('/blocks/create', methods=['POST'])
def create_block():
    """Create a new hostel block."""
    name = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip().upper()
    gender = request.form.get('gender', 'male')
    warden_id = request.form.get('warden_id') or None

    if not name or not code:
        flash('Name and code are required.', 'danger')
        return redirect(url_for('admin.blocks'))

    block = HostelBlock(name=name, code=code, gender=gender,
                        warden_id=int(warden_id) if warden_id else None)
    db.session.add(block)
    db.session.commit()
    log_action('BLOCK_CREATED', 'HostelBlock', block.id)
    flash(f'Block {name} created.', 'success')
    return redirect(url_for('admin.blocks'))


@admin_bp.route('/rooms')
def rooms():
    """Manage rooms."""
    block_id = request.args.get('block_id', type=int)
    if block_id:
        all_rooms = Room.query.filter_by(block_id=block_id).all()
    else:
        all_rooms = Room.query.all()
    all_blocks = HostelBlock.query.all()
    return render_template('admin/rooms.html', rooms=all_rooms, blocks=all_blocks, block_id=block_id)


@admin_bp.route('/rooms/create', methods=['POST'])
def create_room():
    """Create a new room."""
    room_number = request.form.get('room_number', '').strip()
    block_id = int(request.form.get('block_id'))
    floor = int(request.form.get('floor', 0))
    capacity = int(request.form.get('capacity', 2))

    room = Room(room_number=room_number, block_id=block_id, floor=floor, capacity=capacity)
    db.session.add(room)
    db.session.commit()
    flash(f'Room {room_number} created.', 'success')
    return redirect(url_for('admin.rooms'))


# ─── Department Management ───────────────────────────────────────────────────

@admin_bp.route('/departments')
def departments():
    """Manage departments."""
    depts = Department.query.all()
    return render_template('admin/departments.html', departments=depts)


@admin_bp.route('/departments/create', methods=['POST'])
def create_department():
    name = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip().upper()
    if not name or not code:
        flash('Name and code are required.', 'danger')
        return redirect(url_for('admin.departments'))
    dept = Department(name=name, code=code)
    db.session.add(dept)
    db.session.commit()
    flash(f'Department {name} created.', 'success')
    return redirect(url_for('admin.departments'))


# ─── Outpass Types & Rules ───────────────────────────────────────────────────

@admin_bp.route('/outpass-types')
def outpass_types():
    """Manage outpass types and rules."""
    types = OutpassType.query.all()
    return render_template('admin/outpass_types.html', outpass_types=types)


@admin_bp.route('/outpass-types/create', methods=['POST'])
def create_outpass_type():
    otype = OutpassType(
        name=request.form.get('name', '').strip(),
        code=request.form.get('code', '').strip().upper(),
        description=request.form.get('description', ''),
        max_duration_hours=int(request.form.get('max_duration_hours', 24)),
        monthly_limit=int(request.form.get('monthly_limit', 4)),
        requires_parent_confirmation='requires_parent' in request.form,
        approval_chain=request.form.get('approval_chain', 'warden'),
        is_active=True
    )
    db.session.add(otype)
    db.session.commit()
    log_action('OUTPASS_TYPE_CREATED', 'OutpassType', otype.id)
    flash(f'Outpass type "{otype.name}" created.', 'success')
    return redirect(url_for('admin.outpass_types'))


@admin_bp.route('/outpass-types/<int:type_id>/toggle', methods=['POST'])
def toggle_outpass_type(type_id):
    otype = db.session.get(OutpassType, type_id)
    if otype:
        otype.is_active = not otype.is_active
        db.session.commit()
        flash(f'Type "{otype.name}" {"enabled" if otype.is_active else "disabled"}.', 'success')
    return redirect(url_for('admin.outpass_types'))


# ─── Restrictions ────────────────────────────────────────────────────────────

@admin_bp.route('/restrictions')
def restrictions():
    """View and manage student restrictions."""
    restricted = Student.query.filter_by(is_restricted=True).all()
    students = Student.query.all()
    return render_template('admin/restrictions.html', restricted=restricted, students=students)


@admin_bp.route('/restrictions/add', methods=['POST'])
def add_restriction():
    student_id = int(request.form.get('student_id'))
    reason = request.form.get('reason', '').strip()
    duration_days = int(request.form.get('duration_days', 30))

    student = db.session.get(Student, student_id)
    if student:
        student.is_restricted = True
        student.restriction_reason = reason
        student.restricted_until = datetime.utcnow() + timedelta(days=duration_days)
        db.session.commit()
        log_action('STUDENT_RESTRICTED', 'Student', student.id, f'Restricted for: {reason}')
        notify_user(student.user_id, 'Account Restricted',
                    f'Your outpass privileges have been restricted. Reason: {reason}',
                    category='danger')
        flash(f'Student {student.register_number} restricted.', 'success')
    return redirect(url_for('admin.restrictions'))


@admin_bp.route('/restrictions/remove/<int:student_id>', methods=['POST'])
def remove_restriction(student_id):
    student = db.session.get(Student, student_id)
    if student:
        student.is_restricted = False
        student.restriction_reason = None
        student.restricted_until = None
        db.session.commit()
        log_action('RESTRICTION_REMOVED', 'Student', student.id)
        flash(f'Restriction removed for {student.register_number}.', 'success')
    return redirect(url_for('admin.restrictions'))


# ─── Announcements ──────────────────────────────────────────────────────────

@admin_bp.route('/announcements')
def announcements():
    anncs = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template('admin/announcements.html', announcements=anncs)


@admin_bp.route('/announcements/create', methods=['POST'])
def create_announcement():
    annc = Announcement(
        title=request.form.get('title', '').strip(),
        content=request.form.get('content', '').strip(),
        category=request.form.get('category', 'general'),
        created_by=current_user.id
    )
    db.session.add(annc)
    db.session.commit()
    flash('Announcement published.', 'success')
    return redirect(url_for('admin.announcements'))


@admin_bp.route('/announcements/<int:ann_id>/toggle', methods=['POST'])
def toggle_announcement(ann_id):
    annc = db.session.get(Announcement, ann_id)
    if annc:
        annc.is_active = not annc.is_active
        db.session.commit()
    return redirect(url_for('admin.announcements'))


# ─── Audit Log ───────────────────────────────────────────────────────────────

@admin_bp.route('/audit-logs')
def audit_logs():
    page = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', '')
    
    query = AuditLog.query
    if action_filter:
        query = query.filter(AuditLog.action.ilike(f'%{action_filter}%'))
    
    logs = query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=30, error_out=False
    )
    return render_template('admin/audit_logs.html', logs=logs, action_filter=action_filter)


# ─── Reports ────────────────────────────────────────────────────────────────

@admin_bp.route('/reports')
def reports():
    """Analytics and reports page."""
    # Date range
    days = int(request.args.get('days', 30))
    start_date = datetime.utcnow() - timedelta(days=days)

    # Outpasses per day
    daily_data = db.session.query(
        db.func.date(OutpassRequest.created_at),
        db.func.count(OutpassRequest.id)
    ).filter(OutpassRequest.created_at >= start_date).group_by(
        db.func.date(OutpassRequest.created_at)
    ).all()

    # Type distribution
    type_data = db.session.query(
        OutpassType.name,
        db.func.count(OutpassRequest.id)
    ).join(OutpassRequest).filter(
        OutpassRequest.created_at >= start_date
    ).group_by(OutpassType.name).all()

    # Status distribution
    status_data = db.session.query(
        OutpassRequest.status,
        db.func.count(OutpassRequest.id)
    ).filter(OutpassRequest.created_at >= start_date).group_by(
        OutpassRequest.status
    ).all()

    # Department-wise
    dept_data = db.session.query(
        Department.name,
        db.func.count(OutpassRequest.id)
    ).join(Student, Student.department_id == Department.id).join(
        OutpassRequest, OutpassRequest.student_id == Student.id
    ).filter(OutpassRequest.created_at >= start_date).group_by(
        Department.name
    ).all()

    return render_template('admin/reports.html',
                           daily_data=daily_data,
                           type_data=type_data,
                           status_data=status_data,
                           dept_data=dept_data,
                           days=days)


@admin_bp.route('/reports/export-excel')
def export_excel():
    """Export outpass data to Excel."""
    import pandas as pd
    
    days = int(request.args.get('days', 30))
    start_date = datetime.utcnow() - timedelta(days=days)
    
    outpasses = OutpassRequest.query.filter(
        OutpassRequest.created_at >= start_date
    ).all()
    
    data = []
    for op in outpasses:
        data.append({
            'Outpass Number': op.outpass_number,
            'Student': op.student.user.full_name,
            'Register No': op.student.register_number,
            'Department': op.student.department.name if op.student.department else 'N/A',
            'Block': op.student.hostel_block.name if op.student.hostel_block else 'N/A',
            'Type': op.outpass_type.name,
            'Status': op.status,
            'Out DateTime': op.out_datetime.strftime('%d-%m-%Y %H:%M'),
            'Return DateTime': op.expected_return_datetime.strftime('%d-%m-%Y %H:%M'),
            'Actual Out': op.actual_out_datetime.strftime('%d-%m-%Y %H:%M') if op.actual_out_datetime else '',
            'Actual Return': op.actual_return_datetime.strftime('%d-%m-%Y %H:%M') if op.actual_return_datetime else '',
            'Destination': op.destination,
            'Late Return': 'Yes' if op.is_overdue else 'No',
            'Created': op.created_at.strftime('%d-%m-%Y %H:%M'),
        })
    
    df = pd.DataFrame(data)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name='Outpass Report')
    buf.seek(0)
    
    return send_file(
        buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'outpass_report_{datetime.utcnow().strftime("%Y%m%d")}.xlsx'
    )


@admin_bp.route('/reports/chart-data')
def chart_data():
    """Return JSON chart data for AJAX requests."""
    days = int(request.args.get('days', 30))
    start_date = datetime.utcnow() - timedelta(days=days)

    # Daily outpass counts
    daily = db.session.query(
        db.func.date(OutpassRequest.created_at),
        db.func.count(OutpassRequest.id)
    ).filter(OutpassRequest.created_at >= start_date).group_by(
        db.func.date(OutpassRequest.created_at)
    ).all()

    # Peak exit hours
    hour_data = db.session.query(
        db.func.strftime('%H', GateLog.timestamp),
        db.func.count(GateLog.id)
    ).filter(GateLog.action == 'OUT', GateLog.timestamp >= start_date).group_by(
        db.func.strftime('%H', GateLog.timestamp)
    ).all()

    return jsonify({
        'daily': {'labels': [str(d[0]) for d in daily], 'values': [d[1] for d in daily]},
        'peak_hours': {'labels': [f'{h[0]}:00' for h in hour_data], 'values': [h[1] for h in hour_data]},
    })
