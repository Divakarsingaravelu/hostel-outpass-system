"""Outpass-related models."""
from datetime import datetime
from app import db


class OutpassType(db.Model):
    """Types of outpasses with rules."""
    __tablename__ = 'outpass_types'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    max_duration_hours = db.Column(db.Integer, default=24)
    monthly_limit = db.Column(db.Integer, default=4)
    requires_parent_confirmation = db.Column(db.Boolean, default=False)
    approval_chain = db.Column(db.String(256), default='warden')  # e.g., "advisor,warden"
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    outpass_requests = db.relationship('OutpassRequest', backref='outpass_type', lazy='dynamic')

    def get_approval_chain(self):
        """Return list of approval roles in order."""
        return [role.strip() for role in self.approval_chain.split(',') if role.strip()]

    def __repr__(self):
        return f'<OutpassType {self.name}>'


class OutpassRequest(db.Model):
    """Individual outpass request from a student."""
    __tablename__ = 'outpass_requests'

    id = db.Column(db.Integer, primary_key=True)
    outpass_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    type_id = db.Column(db.Integer, db.ForeignKey('outpass_types.id'), nullable=False)
    
    # Request details
    reason = db.Column(db.Text, nullable=False)
    destination = db.Column(db.String(256), nullable=False)
    out_datetime = db.Column(db.DateTime, nullable=False)
    expected_return_datetime = db.Column(db.DateTime, nullable=False)
    contact_number = db.Column(db.String(15), nullable=False)
    attachment_filename = db.Column(db.String(256), nullable=True)
    
    # Status tracking
    status = db.Column(db.String(20), default='PENDING', nullable=False, index=True)
    # PENDING, PARTIALLY_APPROVED, APPROVED, REJECTED, CANCELLED, EXPIRED, OUT, RETURNED, OVERDUE
    current_approval_level = db.Column(db.Integer, default=0)
    
    # Parent confirmation
    parent_confirmed = db.Column(db.Boolean, default=False)
    parent_confirmation_token = db.Column(db.String(128), nullable=True)
    parent_confirmed_at = db.Column(db.DateTime, nullable=True)
    
    # Gate timestamps
    actual_out_datetime = db.Column(db.DateTime, nullable=True)
    actual_return_datetime = db.Column(db.DateTime, nullable=True)
    
    # QR code
    qr_token = db.Column(db.String(256), nullable=True)
    qr_filename = db.Column(db.String(256), nullable=True)
    
    # Flags
    is_emergency = db.Column(db.Boolean, default=False)
    is_overdue = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    approvals = db.relationship('Approval', backref='outpass_request', lazy='dynamic',
                                cascade='all, delete-orphan', order_by='Approval.level')
    gate_logs = db.relationship('GateLog', backref='outpass_request', lazy='dynamic',
                                cascade='all, delete-orphan')

    def get_status_badge_class(self):
        """Return Bootstrap badge class for status."""
        status_classes = {
            'PENDING': 'bg-warning text-dark',
            'PARTIALLY_APPROVED': 'bg-info',
            'APPROVED': 'bg-success',
            'REJECTED': 'bg-danger',
            'CANCELLED': 'bg-secondary',
            'EXPIRED': 'bg-dark',
            'OUT': 'bg-primary',
            'RETURNED': 'bg-success',
            'OVERDUE': 'bg-danger',
        }
        return status_classes.get(self.status, 'bg-secondary')

    def __repr__(self):
        return f'<OutpassRequest {self.outpass_number} - {self.status}>'


class Approval(db.Model):
    """Approval record for each level in the chain."""
    __tablename__ = 'approvals'

    id = db.Column(db.Integer, primary_key=True)
    outpass_id = db.Column(db.Integer, db.ForeignKey('outpass_requests.id'), nullable=False, index=True)
    level = db.Column(db.Integer, nullable=False)  # 1, 2, etc.
    approver_role = db.Column(db.String(20), nullable=False)  # warden, advisor
    approver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(20), default='PENDING', nullable=False)  # PENDING, APPROVED, REJECTED
    remarks = db.Column(db.Text, nullable=True)
    acted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    approver = db.relationship('User', backref='approvals_given')

    def __repr__(self):
        return f'<Approval L{self.level} {self.approver_role} - {self.status}>'
