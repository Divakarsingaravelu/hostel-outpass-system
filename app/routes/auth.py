"""Authentication routes."""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user, login_required
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from app import db, limiter
from app.models.user import User
from app.models.outpass import OutpassRequest
from app.services.audit_service import log_action
from app.services.notification_service import send_email

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    """Landing page — redirect authenticated users to their dashboard."""
    if current_user.is_authenticated:
        return redirect(url_for(_get_dashboard_route(current_user.role)))
    return render_template('auth/login.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    """User login."""
    if current_user.is_authenticated:
        return redirect(url_for(_get_dashboard_route(current_user.role)))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()

        if not user:
            flash('Invalid username or password.', 'danger')
            return render_template('auth/login.html')

        if user.is_locked():
            remaining = (user.locked_until - datetime.utcnow()).seconds // 60
            flash(f'Account locked. Try again in {remaining + 1} minutes.', 'danger')
            return render_template('auth/login.html')

        if not user.check_password(password):
            user.record_failed_login(
                threshold=current_app.config.get('LOCKOUT_THRESHOLD', 5),
                duration_minutes=current_app.config.get('LOCKOUT_DURATION_MINUTES', 15)
            )
            remaining_attempts = current_app.config.get('LOCKOUT_THRESHOLD', 5) - user.failed_login_attempts
            if remaining_attempts > 0:
                flash(f'Invalid password. {remaining_attempts} attempts remaining.', 'danger')
            else:
                flash('Account has been locked due to too many failed attempts.', 'danger')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('Your account has been deactivated. Contact admin.', 'danger')
            return render_template('auth/login.html')

        # Successful login
        user.record_successful_login()
        login_user(user, remember=False)
        log_action('LOGIN', 'User', user.id, f'User {user.username} logged in')

        if user.must_change_password:
            flash('Please change your default password.', 'warning')
            return redirect(url_for('auth.change_password'))

        flash(f'Welcome, {user.full_name}!', 'success')
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for(_get_dashboard_route(user.role)))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """User logout."""
    log_action('LOGOUT', 'User', current_user.id, f'User {current_user.username} logged out')
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password (forced on first login)."""
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not current_user.check_password(current_pw):
            flash('Current password is incorrect.', 'danger')
            return render_template('auth/change_password.html')

        if len(new_pw) < 8:
            flash('New password must be at least 8 characters.', 'danger')
            return render_template('auth/change_password.html')

        if new_pw != confirm_pw:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/change_password.html')

        current_user.set_password(new_pw)
        current_user.must_change_password = False
        db.session.commit()
        log_action('PASSWORD_CHANGED', 'User', current_user.id)
        flash('Password changed successfully!', 'success')
        return redirect(url_for(_get_dashboard_route(current_user.role)))

    return render_template('auth/change_password.html')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def forgot_password():
    """Request password reset link."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()

        if user:
            s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
            token = s.dumps(user.id, salt='password-reset')
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            # Dev mode: print to console
            print(f'\n{"="*50}')
            print(f'PASSWORD RESET LINK (DEV)')
            print(f'User: {user.username}')
            print(f'URL: {reset_url}')
            print(f'{"="*50}\n')
            
            if user.email:
                send_email(user.email, 'Password Reset', f'Reset your password: {reset_url}')
        
        # Always show the same message (security)
        flash('If the account exists, a reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password via token."""
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        user_id = s.loads(token, salt='password-reset',
                         max_age=current_app.config.get('PASSWORD_RESET_EXPIRY', 3600))
    except (SignatureExpired, BadSignature):
        flash('The reset link is invalid or expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if len(new_pw) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('auth/reset_password.html', token=token)

        if new_pw != confirm_pw:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html', token=token)

        user.set_password(new_pw)
        user.must_change_password = False
        db.session.commit()
        log_action('PASSWORD_RESET', 'User', user.id)
        flash('Password has been reset. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)


@auth_bp.route('/parent-confirm/<token>')
def parent_confirm(token):
    """Parent confirmation link for outpass."""
    outpass = OutpassRequest.query.filter_by(parent_confirmation_token=token).first()
    if not outpass:
        flash('Invalid confirmation link.', 'danger')
        return render_template('auth/parent_confirm.html', outpass=None, error=True)
    
    if outpass.parent_confirmed:
        flash('Already confirmed.', 'info')
        return render_template('auth/parent_confirm.html', outpass=outpass, already=True)
    
    outpass.parent_confirmed = True
    outpass.parent_confirmed_at = datetime.utcnow()
    db.session.commit()
    
    flash('Parent confirmation recorded successfully!', 'success')
    return render_template('auth/parent_confirm.html', outpass=outpass, success=True)


def _get_dashboard_route(role):
    """Get the dashboard URL endpoint for a given role."""
    routes = {
        'admin': 'admin.dashboard',
        'student': 'student.dashboard',
        'warden': 'warden.dashboard',
        'advisor': 'warden.dashboard',
        'guard': 'guard.dashboard',
    }
    return routes.get(role, 'auth.login')
