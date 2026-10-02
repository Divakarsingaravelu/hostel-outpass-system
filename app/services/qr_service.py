"""QR code generation and verification service using itsdangerous."""
import io
import os
import qrcode
from datetime import datetime
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from flask import current_app


def _get_serializer():
    """Get the itsdangerous serializer."""
    secret = os.environ.get('QR_SIGNING_SECRET', 'qr-dev-secret')
    return URLSafeTimedSerializer(secret)


def generate_qr_token(outpass):
    """Generate a signed, tamper-proof QR token for an outpass."""
    s = _get_serializer()
    data = {
        'op': outpass.outpass_number,
        'sid': outpass.student_id,
        'exp_out': outpass.out_datetime.isoformat(),
        'exp_ret': outpass.expected_return_datetime.isoformat(),
        'type': outpass.outpass_type.code
    }
    return s.dumps(data)


def verify_qr_token(token, max_age=86400 * 7):
    """Verify a QR token and return the payload.
    
    Returns (is_valid, data_or_error).
    """
    s = _get_serializer()
    try:
        data = s.loads(token, max_age=max_age)
        return True, data
    except SignatureExpired:
        return False, 'QR code has expired.'
    except BadSignature:
        return False, 'Invalid or tampered QR code.'


def generate_qr_image(data_string, outpass_number):
    """Generate QR code image and save to uploads.
    
    Returns the filename.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data_string)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color='black', back_color='white')
    
    filename = f'qr_{outpass_number}.png'
    upload_dir = os.environ.get('UPLOAD_FOLDER', os.path.join('app', 'static', 'uploads'))
    qr_dir = os.path.join(upload_dir, 'qrcodes')
    os.makedirs(qr_dir, exist_ok=True)
    
    filepath = os.path.join(qr_dir, filename)
    img.save(filepath)
    
    return filename


def generate_qr_image_bytes(data_string):
    """Generate QR code image as bytes (for PDF embedding)."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=8,
        border=3,
    )
    qr.add_data(data_string)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf
