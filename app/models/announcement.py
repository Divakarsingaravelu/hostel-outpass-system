"""Announcement model."""
from datetime import datetime
from app import db


class Announcement(db.Model):
    """System-wide announcements."""
    __tablename__ = 'announcements'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(20), default='general')  # general, urgent, maintenance
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)

    author = db.relationship('User', backref='announcements')

    def __repr__(self):
        return f'<Announcement {self.title[:30]}>'
