"""Test configuration and fixtures."""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db as _db
from app.models.user import User, Student, Staff, Department, HostelBlock, Room
from app.models.outpass import OutpassType, OutpassRequest, Approval


@pytest.fixture(scope='session')
def app():
    """Create test application."""
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture(scope='function')
def db(app):
    """Fresh database for each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture
def client(app, db):
    """Test client."""
    return app.test_client()


@pytest.fixture
def setup_data(db):
    """Create basic test data."""
    # Department
    dept = Department(name='Computer Science', code='CSE')
    db.session.add(dept)
    db.session.flush()

    # Block
    block = HostelBlock(name='Test Block', code='TB1', gender='male')
    db.session.add(block)
    db.session.flush()

    # Room
    room = Room(room_number='101', block_id=block.id, floor=1)
    db.session.add(room)
    db.session.flush()

    # Admin
    admin = User(username='admin', role='admin', full_name='Admin User',
                 must_change_password=False)
    admin.set_password('Admin@123')
    db.session.add(admin)
    db.session.flush()

    # Warden
    warden = User(username='warden1', role='warden', full_name='Test Warden',
                  must_change_password=False)
    warden.set_password('Warden@123')
    db.session.add(warden)
    db.session.flush()
    warden_staff = Staff(user_id=warden.id, staff_id='W001',
                         hostel_block_id=block.id, department_id=dept.id)
    db.session.add(warden_staff)
    block.warden_id = warden.id

    # Guard
    guard = User(username='guard1', role='guard', full_name='Test Guard',
                 must_change_password=False)
    guard.set_password('Guard@123')
    db.session.add(guard)
    db.session.flush()
    guard_staff = Staff(user_id=guard.id, staff_id='G001')
    db.session.add(guard_staff)

    # Student
    student_user = User(username='STU001', role='student', full_name='Test Student',
                        phone='9876543210', must_change_password=False)
    student_user.set_password('Student@123')
    db.session.add(student_user)
    db.session.flush()
    student = Student(user_id=student_user.id, register_number='STU001',
                      department_id=dept.id, year=2,
                      hostel_block_id=block.id, room_id=room.id,
                      parent_name='Parent', parent_phone='9123456789')
    db.session.add(student)

    # Outpass types
    local_type = OutpassType(name='Local', code='LOCAL', max_duration_hours=6,
                             monthly_limit=4, approval_chain='warden')
    vacation_type = OutpassType(name='Vacation', code='VACATION', max_duration_hours=720,
                                monthly_limit=2, requires_parent_confirmation=True,
                                approval_chain='advisor,warden')
    emergency_type = OutpassType(name='Emergency', code='EMERGENCY', max_duration_hours=24,
                                 monthly_limit=10, approval_chain='warden')
    db.session.add_all([local_type, vacation_type, emergency_type])
    db.session.commit()

    return {
        'admin': admin, 'warden': warden, 'guard': guard,
        'student_user': student_user, 'student': student,
        'dept': dept, 'block': block, 'room': room,
        'local_type': local_type, 'vacation_type': vacation_type,
        'emergency_type': emergency_type,
    }


def login(client, username, password):
    """Helper to log in a user."""
    return client.post('/login', data={
        'username': username, 'password': password
    }, follow_redirects=True)


def logout(client):
    """Helper to log out."""
    return client.get('/logout', follow_redirects=True)
