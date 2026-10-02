"""Audit logging service."""
from flask import request
from flask_login import current_user
from app import db
from app.models.audit_log import AuditLog


def log_action(action, entity_type=None, entity_id=None, details=None, user_id=None):
    """Record an action in the audit log.
    
    Args:
        action: Short description of the action (e.g., 'OUTPASS_CREATED')
        entity_type: Type of entity involved (e.g., 'OutpassRequest')
        entity_id: ID of the entity
        details: Additional details string
        user_id: Override user ID (defaults to current_user)
    """
    uid = user_id
    if uid is None and current_user and current_user.is_authenticated:
        uid = current_user.id
    
    ip = request.remote_addr if request else None
    
    log = AuditLog(
        user_id=uid,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip
    )
    db.session.add(log)
    db.session.commit()
    return log
