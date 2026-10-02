"""Tests for authentication and role-based access."""
from tests.conftest import login, logout


class TestAuth:
    """Authentication tests."""

    def test_login_page_loads(self, client):
        """Login page should render successfully."""
        rv = client.get('/login')
        assert rv.status_code == 200
        assert b'Hostel Outpass' in rv.data

    def test_login_valid_credentials(self, client, setup_data):
        """Valid credentials should log in successfully."""
        rv = login(client, 'STU001', 'Student@123')
        assert rv.status_code == 200
        assert b'Dashboard' in rv.data or b'Welcome' in rv.data

    def test_login_invalid_password(self, client, setup_data):
        """Invalid password should fail."""
        rv = login(client, 'STU001', 'wrong')
        assert b'Invalid' in rv.data or b'password' in rv.data

    def test_login_nonexistent_user(self, client, setup_data):
        """Non-existent user should fail."""
        rv = login(client, 'nobody', 'test')
        assert b'Invalid' in rv.data

    def test_logout(self, client, setup_data):
        """Logout should redirect to login."""
        login(client, 'STU001', 'Student@123')
        rv = logout(client)
        assert rv.status_code == 200

    def test_account_lockout(self, client, setup_data):
        """Account should lock after threshold failed attempts."""
        for _ in range(5):
            login(client, 'STU001', 'wrong')
        rv = login(client, 'STU001', 'wrong')
        assert b'locked' in rv.data.lower() or b'Locked' in rv.data


class TestRoleAccess:
    """Role-based access control tests."""

    def test_student_cannot_access_admin(self, client, setup_data):
        """Student should get 403 on admin routes."""
        login(client, 'STU001', 'Student@123')
        rv = client.get('/admin/dashboard')
        assert rv.status_code == 403

    def test_student_cannot_access_warden(self, client, setup_data):
        """Student should get 403 on warden routes."""
        login(client, 'STU001', 'Student@123')
        rv = client.get('/warden/dashboard')
        assert rv.status_code == 403

    def test_guard_cannot_access_admin(self, client, setup_data):
        """Guard should get 403 on admin routes."""
        login(client, 'guard1', 'Guard@123')
        rv = client.get('/admin/dashboard')
        assert rv.status_code == 403

    def test_warden_can_access_dashboard(self, client, setup_data):
        """Warden should access their dashboard."""
        login(client, 'warden1', 'Warden@123')
        rv = client.get('/warden/dashboard')
        assert rv.status_code == 200

    def test_admin_can_access_dashboard(self, client, setup_data):
        """Admin should access admin dashboard."""
        login(client, 'admin', 'Admin@123')
        rv = client.get('/admin/dashboard')
        assert rv.status_code == 200

    def test_unauthenticated_redirects(self, client):
        """Unauthenticated user should be redirected to login."""
        rv = client.get('/student/dashboard')
        assert rv.status_code == 302
