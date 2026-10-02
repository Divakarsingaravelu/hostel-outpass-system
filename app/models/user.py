"""User and role models."""
from datetime import datetime, timedelta
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
    """Base user model for all roles."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)  # admin, student, warden, advisor, guard
    full_name = db.Column(db.String(128), nullable=False)
    phone = db.Column(db.String(15), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    must_change_password = db.Column(db.Boolean, default=True)
    photo_filename = db.Column(db.String(256), nullable=True)
    
    # Account lockout
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    # Relationships
    student_profile = db.relationship('Student', backref='user', uselist=False, cascade='all, delete-orphan')
    staff_profile = db.relationship('Staff', backref='user', uselist=False, cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic')

    def set_password(self, password):
        """Hash and set the user password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify password against hash."""
        return check_password_hash(self.password_hash, password)

    def is_locked(self):
        """Check if account is currently locked."""
        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        if self.locked_until and self.locked_until <= datetime.utcnow():
            # Lockout expired, reset
            self.failed_login_attempts = 0
            self.locked_until = None
            db.session.commit()
        return False

    def record_failed_login(self, threshold=5, duration_minutes=15):
        """Record a failed login attempt. Lock if threshold exceeded."""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= threshold:
            self.locked_until = datetime.utcnow() + timedelta(minutes=duration_minutes)
        db.session.commit()

    def record_successful_login(self):
        """Reset failed attempts on successful login."""
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login = datetime.utcnow()
        db.session.commit()

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class Student(db.Model):
    """Student profile extending User."""
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    register_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    year = db.Column(db.Integer, nullable=True)  # 1-4
    hostel_block_id = db.Column(db.Integer, db.ForeignKey('hostel_blocks.id'), nullable=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=True)
    blood_group = db.Column(db.String(5), nullable=True)
    parent_name = db.Column(db.String(128), nullable=True)
    parent_phone = db.Column(db.String(15), nullable=True)
    parent_email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    is_restricted = db.Column(db.Boolean, default=False)
    restriction_reason = db.Column(db.Text, nullable=True)
    restricted_until = db.Column(db.DateTime, nullable=True)

    # Relationships
    department = db.relationship('Department', backref='students')
    hostel_block = db.relationship('HostelBlock', backref='students')
    room = db.relationship('Room', backref='students')
    outpass_requests = db.relationship('OutpassRequest', backref='student', lazy='dynamic', cascade='all, delete-orphan')

    def is_currently_restricted(self):
        """Check if student is currently under restriction."""
        if not self.is_restricted:
            return False
        if self.restricted_until and self.restricted_until <= datetime.utcnow():
            self.is_restricted = False
            self.restriction_reason = None
            self.restricted_until = None
            db.session.commit()
            return False
        return True

    def __repr__(self):
        return f'<Student {self.register_number}>'


class Staff(db.Model):
    """Staff profile extending User (wardens, advisors, guards, admin)."""
    __tablename__ = 'staff'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    staff_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    designation = db.Column(db.String(64), nullable=True)
    hostel_block_id = db.Column(db.Integer, db.ForeignKey('hostel_blocks.id'), nullable=True)  # For wardens

    department = db.relationship('Department', backref='staff_members')
    hostel_block = db.relationship('HostelBlock', backref='staff_members')

    def __repr__(self):
        return f'<Staff {self.staff_id}>'


class Department(db.Model):
    """Academic department."""
    __tablename__ = 'departments'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    code = db.Column(db.String(10), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Department {self.code}>'


class HostelBlock(db.Model):
    """Hostel block/building."""
    __tablename__ = 'hostel_blocks'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    code = db.Column(db.String(10), unique=True, nullable=False)
    gender = db.Column(db.String(10), default='male')  # male, female
    total_rooms = db.Column(db.Integer, default=0)
    warden_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    warden = db.relationship('User', foreign_keys=[warden_id])
    rooms = db.relationship('Room', backref='hostel_block', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<HostelBlock {self.name}>'


class Room(db.Model):
    """Individual room in a hostel block."""
    __tablename__ = 'rooms'

    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(10), nullable=False)
    block_id = db.Column(db.Integer, db.ForeignKey('hostel_blocks.id'), nullable=False)
    floor = db.Column(db.Integer, default=0)
    capacity = db.Column(db.Integer, default=2)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('room_number', 'block_id', name='uq_room_block'),
    )

    def __repr__(self):
        return f'<Room {self.room_number}>'
