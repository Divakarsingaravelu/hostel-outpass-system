"""Gate log model for tracking student movement."""
from datetime import datetime
from app import db


class GateLog(db.Model):
    """Records gate entry/exit events."""
    __tablename__ = 'gate_logs'

    id = db.Column(db.Integer, primary_key=True)
    outpass_id = db.Column(db.Integer, db.ForeignKey('outpass_requests.id'), nullable=False, index=True)
    guard_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(5), nullable=False)  # OUT, IN
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    remarks = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)

    guard = db.relationship('User', backref='gate_actions')

    def __repr__(self):
        return f'<GateLog {self.action} @ {self.timestamp}>'
