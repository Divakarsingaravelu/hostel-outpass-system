"""Input validators for server-side validation."""
import os
import re
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB


def validate_outpass_form(data, student):
    """Validate outpass application form data.
    
    Returns (is_valid, errors) tuple.
    """
    errors = []

    # Reason
    reason = data.get('reason', '').strip()
    if len(reason) < 15:
        errors.append('Reason must be at least 15 characters long.')

    # Destination
    destination = data.get('destination', '').strip()
    if not destination:
        errors.append('Destination is required.')

    # Dates
    try:
        out_dt = datetime.strptime(data.get('out_datetime', ''), '%Y-%m-%dT%H:%M')
        return_dt = datetime.strptime(data.get('expected_return_datetime', ''), '%Y-%m-%dT%H:%M')
    except (ValueError, TypeError):
        errors.append('Valid departure and return dates/times are required.')
        return False, errors

    now = datetime.utcnow()
    if out_dt < now:
        errors.append('Departure date/time cannot be in the past.')
    if return_dt <= out_dt:
        errors.append('Return date/time must be after departure.')

    # Contact
    contact = data.get('contact_number', '').strip()
    if not re.match(r'^\+?\d{10,15}$', contact):
        errors.append('Valid contact number is required (10-15 digits).')

    return len(errors) == 0, errors


def validate_file_upload(file_storage):
    """Validate an uploaded file for extension and size.
    
    Returns (is_valid, error_message, safe_filename) tuple.
    """
    if not file_storage or file_storage.filename == '':
        return True, None, None  # No file is OK

    filename = secure_filename(file_storage.filename)
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    
    if ext not in ALLOWED_EXTENSIONS:
        return False, f'File type .{ext} not allowed. Use: {", ".join(ALLOWED_EXTENSIONS)}', None

    # Check file size by reading content
    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    
    if size > MAX_FILE_SIZE:
        return False, f'File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)} MB.', None

    # Generate random filename to prevent directory traversal
    safe_name = f'{uuid.uuid4().hex}.{ext}'
    return True, None, safe_name


def validate_phone(phone):
    """Validate phone number format."""
    if not phone:
        return False
    return bool(re.match(r'^\+?\d{10,15}$', phone.strip()))


def sanitize_string(value, max_length=256):
    """Sanitize string input."""
    if not value:
        return ''
    return str(value).strip()[:max_length]
