"""Notification model."""
from datetime import datetime
from app import db


class Notification(db.Model):
    """In-app notification for users."""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(128), nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(20), default='info')  # info, success, warning, danger
    link = db.Column(db.String(256), nullable=True)
    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f'<Notification {self.title[:30]}>'
