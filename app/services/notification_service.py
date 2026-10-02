"""Notification service - in-app + email (console fallback in dev)."""
import os
from datetime import datetime
from app import db
from app.models.notification import Notification


def notify_user(user_id, title, message, category='info', link=None):
    """Create an in-app notification for a user."""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        category=category,
        link=link
    )
    db.session.add(notification)
    db.session.commit()
    return notification


def notify_parent(student, outpass, token):
    """Send parent confirmation request (simulated via console in dev)."""
    parent_name = student.parent_name or 'Parent'
    parent_phone = student.parent_phone or 'N/A'
    student_name = student.user.full_name
    confirm_url = f'/auth/parent-confirm/{token}'

    print(f'[PARENT CONFIRMATION - DEV]')
    print(f'  To: {parent_name} ({parent_phone})')
    print(f'  Student: {student_name}')
    print(f'  Outpass: {outpass.outpass_number}')
    print(f'  Type: {outpass.outpass_type.name}')
    print(f'  Destination: {outpass.destination}')
    print(f'  Out: {outpass.out_datetime.strftime("%d-%m-%Y %H:%M")}')
    print(f'  Return: {outpass.expected_return_datetime.strftime("%d-%m-%Y %H:%M")}')
    print(f'  Confirm URL: {confirm_url}')


def send_email(to, subject, body):
    """Send an email (console fallback in dev mode)."""
    mail_user = os.environ.get('MAIL_USERNAME', '')

    if not mail_user:
        print(f'[EMAIL - DEV CONSOLE]')
        print(f'  To: {to}')
        print(f'  Subject: {subject}')
        print(f'  Body: {body[:200]}')
        return True

    try:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = os.environ.get('MAIL_DEFAULT_SENDER', '')
        msg['To'] = to

        server = smtplib.SMTP(
            os.environ.get('MAIL_SERVER', 'smtp.gmail.com'),
            int(os.environ.get('MAIL_PORT', 587))
        )
        server.starttls()
        server.login(mail_user, os.environ.get('MAIL_PASSWORD', ''))
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f'Email send failed: {e}')
        return False


def send_overdue_alert(student, outpass):
    """Send overdue alert to warden and parent."""
    student_name = student.user.full_name

    if student.parent_email:
        send_email(
            student.parent_email,
            f'URGENT: {student_name} has not returned to hostel',
            f'Your ward {student_name} (Outpass: {outpass.outpass_number}) '
            f'has not returned by the expected time of '
            f'{outpass.expected_return_datetime.strftime("%d-%m-%Y %H:%M")}. '
            f'Please contact them immediately.'
        )

    if student.parent_phone:
        print(f'[SMS ALERT] To: {student.parent_phone} - '
              f'{student_name} OVERDUE. Expected return: '
              f'{outpass.expected_return_datetime.strftime("%d-%m-%Y %H:%M")}')
