"""Tests for outpass business logic and services."""
from datetime import datetime, timedelta
from app.models.outpass import OutpassRequest, OutpassType, Approval
from app.services.outpass_service import (
    can_apply_outpass, create_outpass_request, check_monthly_limit,
    check_overlap, process_approval, cancel_outpass
)
from app.services.qr_service import generate_qr_token, verify_qr_token
from app import db
from tests.conftest import login


class TestOutpassValidation:
    """Outpass creation validation tests."""

    def test_can_apply_when_eligible(self, app, setup_data):
        """Student with no active outpass should be able to apply."""
        with app.app_context():
            student = setup_data['student']
            can, reason = can_apply_outpass(student)
            assert can is True

    def test_cannot_apply_with_active_outpass(self, app, setup_data):
        """Student with active outpass should not apply."""
        with app.app_context():
            student = setup_data['student']
            # Create an active outpass
            op = OutpassRequest(
                outpass_number='OP-TEST-0001',
                student_id=student.id,
                type_id=setup_data['local_type'].id,
                reason='Test outpass for validation',
                destination='Test destination',
                out_datetime=datetime.utcnow() + timedelta(hours=1),
                expected_return_datetime=datetime.utcnow() + timedelta(hours=5),
                contact_number='9876543210',
                status='APPROVED'
            )
            db.session.add(op)
            db.session.commit()

            can, reason = can_apply_outpass(student)
            assert can is False
            assert 'active' in reason.lower()

    def test_cannot_apply_with_pending_request(self, app, setup_data):
        """Student with pending request should not apply."""
        with app.app_context():
            student = setup_data['student']
            op = OutpassRequest(
                outpass_number='OP-TEST-0002',
                student_id=student.id,
                type_id=setup_data['local_type'].id,
                reason='Pending test outpass request',
                destination='Test',
                out_datetime=datetime.utcnow() + timedelta(hours=1),
                expected_return_datetime=datetime.utcnow() + timedelta(hours=5),
                contact_number='9876543210',
                status='PENDING'
            )
            db.session.add(op)
            db.session.commit()

            can, reason = can_apply_outpass(student)
            assert can is False
            assert 'pending' in reason.lower()

    def test_restricted_student_cannot_apply(self, app, setup_data):
        """Restricted student should not apply."""
        with app.app_context():
            student = setup_data['student']
            student.is_restricted = True
            student.restriction_reason = 'Disciplinary action'
            student.restricted_until = datetime.utcnow() + timedelta(days=30)
            db.session.commit()

            can, reason = can_apply_outpass(student)
            assert can is False
            assert 'restricted' in reason.lower()

            # Cleanup
            student.is_restricted = False
            db.session.commit()

    def test_monthly_limit_check(self, app, setup_data):
        """Monthly limit should be enforced."""
        with app.app_context():
            student = setup_data['student']
            local_type = setup_data['local_type']
            within, count, limit = check_monthly_limit(student, local_type)
            assert within is True
            assert limit == 4

    def test_overlap_detection(self, app, setup_data):
        """Overlapping dates should be detected."""
        with app.app_context():
            student = setup_data['student']
            now = datetime.utcnow()
            
            # Create existing outpass
            op = OutpassRequest(
                outpass_number='OP-TEST-OVERLAP',
                student_id=student.id,
                type_id=setup_data['local_type'].id,
                reason='Existing outpass for overlap test',
                destination='Test',
                out_datetime=now + timedelta(hours=1),
                expected_return_datetime=now + timedelta(hours=5),
                contact_number='9876543210',
                status='APPROVED'
            )
            db.session.add(op)
            db.session.commit()

            # Check overlap
            has_overlap = check_overlap(student, now + timedelta(hours=2), now + timedelta(hours=6))
            assert has_overlap is True

            # Check no overlap
            no_overlap = check_overlap(student, now + timedelta(hours=6), now + timedelta(hours=10))
            assert no_overlap is False


class TestApprovalWorkflow:
    """Approval chain tests."""

    def test_warden_approval(self, app, setup_data):
        """Warden should be able to approve local outpass."""
        with app.app_context():
            student = setup_data['student']
            warden = setup_data['warden']
            form_data = {
                'type_id': setup_data['local_type'].id,
                'reason': 'Need to go for shopping supplies',
                'destination': 'City Market',
                'out_datetime': (datetime.utcnow() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),
                'expected_return_datetime': (datetime.utcnow() + timedelta(hours=5)).strftime('%Y-%m-%dT%H:%M'),
                'contact_number': '9876543210'
            }
            outpass, error = create_outpass_request(student, form_data)
            assert error is None
            assert outpass.status == 'PENDING'

            # Approve
            success, msg = process_approval(outpass, warden, 'APPROVED', 'OK')
            assert success is True
            assert outpass.status == 'APPROVED'

    def test_rejection_requires_remarks(self, app, setup_data):
        """Rejection without remarks should fail."""
        with app.app_context():
            student = setup_data['student']
            warden = setup_data['warden']
            form_data = {
                'type_id': setup_data['local_type'].id,
                'reason': 'Need to go for shopping items',
                'destination': 'Mall',
                'out_datetime': (datetime.utcnow() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),
                'expected_return_datetime': (datetime.utcnow() + timedelta(hours=5)).strftime('%Y-%m-%dT%H:%M'),
                'contact_number': '9876543210'
            }
            outpass, _ = create_outpass_request(student, form_data)
            success, msg = process_approval(outpass, warden, 'REJECTED', '')
            assert success is False
            assert 'remarks' in msg.lower() or 'mandatory' in msg.lower()

    def test_cancel_pending_outpass(self, app, setup_data):
        """Student should be able to cancel pending request."""
        with app.app_context():
            student = setup_data['student']
            form_data = {
                'type_id': setup_data['local_type'].id,
                'reason': 'Test cancel outpass request',
                'destination': 'Test',
                'out_datetime': (datetime.utcnow() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),
                'expected_return_datetime': (datetime.utcnow() + timedelta(hours=5)).strftime('%Y-%m-%dT%H:%M'),
                'contact_number': '9876543210'
            }
            outpass, _ = create_outpass_request(student, form_data)
            success, msg = cancel_outpass(outpass, student.user_id)
            assert success is True
            assert outpass.status == 'CANCELLED'


class TestQRService:
    """QR code generation and verification tests."""

    def test_generate_and_verify_token(self, app, setup_data):
        """Token should be generated and verified successfully."""
        with app.app_context():
            student = setup_data['student']
            op = OutpassRequest(
                outpass_number='OP-QR-TEST',
                student_id=student.id,
                type_id=setup_data['local_type'].id,
                reason='QR test outpass generation test',
                destination='Test',
                out_datetime=datetime.utcnow(),
                expected_return_datetime=datetime.utcnow() + timedelta(hours=5),
                contact_number='9876543210',
                status='APPROVED'
            )
            db.session.add(op)
            db.session.commit()

            token = generate_qr_token(op)
            assert token is not None

            is_valid, data = verify_qr_token(token)
            assert is_valid is True
            assert data['op'] == 'OP-QR-TEST'

    def test_tampered_token_rejected(self, app):
        """Tampered token should be rejected."""
        with app.app_context():
            is_valid, error = verify_qr_token('tampered.token.value')
            assert is_valid is False
            assert 'Invalid' in error or 'tampered' in error.lower()
