"""Seed script — populate the database with demo data.

Usage: python seed.py
"""
import os
import sys
import random
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User, Student, Staff, Department, HostelBlock, Room
from app.models.outpass import OutpassType, OutpassRequest, Approval
from app.models.gate_log import GateLog
from app.models.announcement import Announcement
from app.models.setting import Setting
from app.services.qr_service import generate_qr_token


def seed():
    """Populate the database with sample data."""
    app = create_app('development')
    with app.app_context():
        # Drop and recreate
        db.drop_all()
        db.create_all()
        print('[OK] Database tables created')

        # ___ Departments _________________________________
        departments = []
        dept_data = [
            ('Computer Science & Engineering', 'CSE'),
            ('Electronics & Communication', 'ECE'),
            ('Mechanical Engineering', 'MECH'),
            ('Electrical Engineering', 'EEE'),
            ('Civil Engineering', 'CIVIL'),
            ('Information Technology', 'IT'),
        ]
        for name, code in dept_data:
            d = Department(name=name, code=code)
            db.session.add(d)
            departments.append(d)
        db.session.flush()
        print(f'[OK] {len(departments)} departments created')

        # ___ Hostel Blocks _______________________________
        blocks = []
        block_data = [
            ('Boys Hostel 1', 'BH1', 'male'),
            ('Boys Hostel 2', 'BH2', 'male'),
            ('Girls Hostel 1', 'GH1', 'female'),
        ]
        for name, code, gender in block_data:
            b = HostelBlock(name=name, code=code, gender=gender, total_rooms=20)
            db.session.add(b)
            blocks.append(b)
        db.session.flush()
        print(f'[OK] {len(blocks)} hostel blocks created')

        # ___ Rooms _______________________________________
        rooms = []
        for block in blocks:
            for floor in range(1, 4):
                for room_num in range(1, 8):
                    r = Room(room_number=f'{floor}0{room_num}', block_id=block.id,
                             floor=floor, capacity=2)
                    db.session.add(r)
                    rooms.append(r)
        db.session.flush()
        print(f'[OK] {len(rooms)} rooms created')

        # ___ Admin User _________________________________
        admin = User(username='admin', email='admin@college.edu', role='admin',
                     full_name='System Administrator', phone='9000000001',
                     must_change_password=False)
        admin.set_password('Admin@123')
        db.session.add(admin)
        db.session.flush()
        Staff(user_id=admin.id, staff_id='ADMIN001', designation='System Admin')
        db.session.flush()
        print('[OK] Admin user created')

        # ___ Wardens _____________________________________
        warden_names = [
            ('Dr. Rajesh Kumar', 'warden1', 'rajesh@college.edu', 0),
            ('Dr. Meena Sharma', 'warden2', 'meena@college.edu', 1),
        ]
        wardens = []
        for name, uname, email, bidx in warden_names:
            w = User(username=uname, email=email, role='warden',
                     full_name=name, phone=f'900000100{bidx}',
                     must_change_password=False)
            w.set_password('Warden@123')
            db.session.add(w)
            db.session.flush()
            staff = Staff(user_id=w.id, staff_id=uname.upper(),
                         department_id=departments[0].id,
                         designation='Hostel Warden',
                         hostel_block_id=blocks[bidx].id)
            db.session.add(staff)
            blocks[bidx].warden_id = w.id
            wardens.append(w)
        db.session.flush()
        print('[OK] 2 wardens created')

        # ___ Advisor _____________________________________
        advisor = User(username='advisor1', email='advisor@college.edu', role='advisor',
                       full_name='Prof. Lakshmi Narayanan', phone='9000002001',
                       must_change_password=False)
        advisor.set_password('Advisor@123')
        db.session.add(advisor)
        db.session.flush()
        Staff(user_id=advisor.id, staff_id='ADV001',
              department_id=departments[0].id, designation='Class Advisor')
        db.session.flush()
        print('[OK] 1 advisor created')

        # ___ Guards ______________________________________
        guard_names = [('Suresh Babu', 'guard1'), ('Ravi Shankar', 'guard2')]
        guards = []
        for name, uname in guard_names:
            g = User(username=uname, email=f'{uname}@college.edu', role='guard',
                     full_name=name, phone=f'9000003001',
                     must_change_password=False)
            g.set_password('Guard@123')
            db.session.add(g)
            guards.append(g)
        db.session.flush()
        for g in guards:
            Staff(user_id=g.id, staff_id=g.username.upper(), designation='Security Guard')
        db.session.flush()
        print('[OK] 2 guards created')

        # ___ Outpass Types _______________________________
        types = []
        type_data = [
            ('Local Outing', 'LOCAL', 6, 8, False, 'warden', 'Same-day local outpass'),
            ('Late Night', 'LATE_NIGHT', 12, 4, True, 'warden', 'Late night outing'),
            ('Weekend Home', 'WEEKEND', 72, 4, True, 'warden', 'Weekend home visit'),
            ('Emergency', 'EMERGENCY', 24, 10, False, 'warden', 'Emergency leave'),
            ('Medical', 'MEDICAL', 48, 10, False, 'warden', 'Medical leave with certificate'),
            ('Vacation / Long Leave', 'VACATION', 720, 2, True, 'advisor,warden', 'Semester break or long leave'),
        ]
        for name, code, hours, limit, parent, chain, desc in type_data:
            t = OutpassType(name=name, code=code, max_duration_hours=hours,
                           monthly_limit=limit, requires_parent_confirmation=parent,
                           approval_chain=chain, description=desc)
            db.session.add(t)
            types.append(t)
        db.session.flush()
        print(f'[OK] {len(types)} outpass types created')

        # ___ Students (30) ______________________________
        indian_names = [
            'Arjun Patel', 'Priya Sharma', 'Vikram Singh', 'Ananya Gupta',
            'Rahul Verma', 'Sneha Reddy', 'Aditya Nair', 'Kavitha Menon',
            'Karthik Sundaram', 'Divya Krishnan', 'Rohan Mehta', 'Pooja Iyer',
            'Siddharth Das', 'Lakshmi Pillai', 'Abhishek Joshi', 'Neha Saxena',
            'Pranav Hegde', 'Rithika Rao', 'Varun Chakraborty', 'Swathi Bhat',
            'Harish Gowda', 'Meghana Shetty', 'Nikhil Agarwal', 'Shruti Pandey',
            'Ajay Kulkarni', 'Deepika Naidu', 'Manish Tiwari', 'Anjali Deshmukh',
            'Suraj Mohan', 'Fatima Begum',
        ]
        parent_names = [
            'Ramesh Patel', 'Suresh Sharma', 'Harjeet Singh', 'Manoj Gupta',
            'Dinesh Verma', 'Venkat Reddy', 'Gopinath Nair', 'Krishna Menon',
            'Sundaram K', 'Krishnan S', 'Rajesh Mehta', 'Iyer R',
            'Subhas Das', 'Pillai M', 'Mahesh Joshi', 'Ajay Saxena',
            'Hegde R', 'Rao Venkat', 'Arnab Chakraborty', 'Ramesh Bhat',
            'Gowda H', 'Shetty R', 'Prakash Agarwal', 'Om Pandey',
            'Kulkarni V', 'Naidu S', 'Tiwari G', 'Deshmukh P',
            'Mohan K', 'Ahmed Khan',
        ]

        students = []
        for i, name in enumerate(indian_names):
            reg = f'STU{str(i+1).zfill(3)}'
            block_idx = i % len(blocks)
            room_idx = i % len(rooms)
            dept_idx = i % len(departments)

            u = User(username=reg, email=f'{reg.lower()}@student.college.edu',
                     role='student', full_name=name,
                     phone=f'98765{str(i).zfill(5)}',
                     must_change_password=False)
            u.set_password('Student@123')
            db.session.add(u)
            db.session.flush()

            s = Student(
                user_id=u.id,
                register_number=reg,
                department_id=departments[dept_idx].id,
                year=random.choice([1, 2, 3, 4]),
                hostel_block_id=blocks[block_idx].id,
                room_id=rooms[room_idx].id,
                blood_group=random.choice(['A+', 'B+', 'O+', 'AB+', 'A-', 'B-', 'O-']),
                parent_name=parent_names[i],
                parent_phone=f'94321{str(i).zfill(5)}',
                parent_email=f'parent{i+1}@gmail.com',
                address=f'{random.randint(1,99)}, {random.choice(["MG Road","Anna Nagar","Koramangala","T Nagar","Banjara Hills"])}, {random.choice(["Chennai","Bangalore","Hyderabad","Mumbai","Delhi"])}',
            )
            db.session.add(s)
            students.append(s)
        db.session.flush()
        print(f'[OK] {len(students)} students created')

        # ___ Sample Outpasses (60) _______________________
        statuses = ['PENDING', 'APPROVED', 'REJECTED', 'OUT', 'RETURNED', 'OVERDUE', 'CANCELLED', 'EXPIRED']
        outpass_count = 0
        now = datetime.utcnow()

        for i in range(60):
            student = random.choice(students)
            otype = random.choice(types)
            status = random.choice(statuses)
            
            days_ago = random.randint(0, 30)
            out_dt = now - timedelta(days=days_ago, hours=random.randint(0, 12))
            return_dt = out_dt + timedelta(hours=random.randint(2, otype.max_duration_hours))

            op_num = f'OP-{out_dt.strftime("%Y%m%d")}-{random.randint(1000,9999):04X}'

            op = OutpassRequest(
                outpass_number=op_num,
                student_id=student.id,
                type_id=otype.id,
                reason=random.choice([
                    'Going home for family function',
                    'Medical checkup at city hospital',
                    'Weekend visit to parents',
                    'Project work at library',
                    'Emergency family situation',
                    'Cultural event in the city',
                    'Internship interview preparation',
                    'Religious festival at hometown',
                    'Dental appointment scheduled',
                    'Sister wedding ceremony at home',
                ]),
                destination=random.choice([
                    'Chennai Central', 'Bangalore City', 'Home - Hyderabad',
                    'Apollo Hospital', 'City Library', 'Railway Station',
                    'Home - Coimbatore', 'Home - Madurai', 'Market Area',
                ]),
                out_datetime=out_dt,
                expected_return_datetime=return_dt,
                contact_number=student.user.phone,
                status=status,
                is_emergency=(otype.code == 'EMERGENCY'),
                created_at=out_dt - timedelta(hours=random.randint(1, 24)),
            )

            # Set actual times for completed outpasses
            if status in ('OUT', 'RETURNED', 'OVERDUE'):
                op.actual_out_datetime = out_dt + timedelta(minutes=random.randint(0, 30))
                if status == 'RETURNED':
                    op.actual_return_datetime = return_dt + timedelta(minutes=random.randint(-60, 120))
                    op.is_overdue = op.actual_return_datetime > return_dt
                elif status == 'OVERDUE':
                    op.is_overdue = True

            db.session.add(op)
            db.session.flush()

            # Generate QR for approved/out/returned
            if status in ('APPROVED', 'OUT', 'RETURNED', 'OVERDUE'):
                op.qr_token = generate_qr_token(op) if hasattr(op, 'outpass_number') else None
                # We'll set this after flush since we need the ORM object
                op.parent_confirmed = otype.requires_parent_confirmation
                if op.parent_confirmed:
                    op.parent_confirmed_at = out_dt - timedelta(hours=2)


            # Create approval records
            chain = otype.get_approval_chain()
            for level, role in enumerate(chain, 1):
                approval_status = 'PENDING'
                approver_id = None
                acted_at = None
                remarks = ''

                if status in ('APPROVED', 'OUT', 'RETURNED', 'OVERDUE', 'PARTIALLY_APPROVED'):
                    approval_status = 'APPROVED'
                    approver_id = wardens[0].id if role == 'warden' else advisor.id
                    acted_at = op.created_at + timedelta(hours=random.randint(1, 4))
                    remarks = random.choice(['Approved', 'OK', 'Verified', 'Approved. Be safe.'])
                elif status == 'REJECTED':
                    if level == 1:
                        approval_status = 'REJECTED'
                        approver_id = wardens[0].id if role == 'warden' else advisor.id
                        acted_at = op.created_at + timedelta(hours=1)
                        remarks = random.choice(['Insufficient reason', 'Exam period', 'Restrict list', 'Not allowed during weekdays'])

                a = Approval(
                    outpass_id=op.id, level=level, approver_role=role,
                    approver_id=approver_id, status=approval_status,
                    remarks=remarks, acted_at=acted_at
                )
                db.session.add(a)

            # Gate logs for OUT/RETURNED
            if status in ('OUT', 'RETURNED', 'OVERDUE') and op.actual_out_datetime:
                gl = GateLog(outpass_id=op.id, guard_id=guards[0].id,
                            action='OUT', timestamp=op.actual_out_datetime,
                            ip_address='192.168.1.100')
                db.session.add(gl)
            if status == 'RETURNED' and op.actual_return_datetime:
                gl2 = GateLog(outpass_id=op.id, guard_id=guards[0].id,
                             action='IN', timestamp=op.actual_return_datetime,
                             ip_address='192.168.1.100')
                db.session.add(gl2)

            outpass_count += 1

        db.session.flush()
        print(f'[OK] {outpass_count} sample outpasses created')

        # ___ Announcements ______________________________
        Announcement(title='Welcome to Digital Outpass System',
                     content='The new digital outpass system is now live. Please use this portal for all outpass requests.',
                     category='general', created_by=admin.id, is_active=True)
        Announcement(title='Gate Timing Update',
                     content='Gate closing time has been updated to 9:00 PM on weekdays and 10:00 PM on weekends.',
                     category='urgent', created_by=admin.id, is_active=True)
        db.session.add_all([
            Announcement(title='Welcome to Digital Outpass System',
                         content='The new digital outpass system is now live.',
                         category='general', created_by=admin.id, is_active=True),
            Announcement(title='Gate Timing Update',
                         content='Gate closes at 9 PM weekdays, 10 PM weekends.',
                         category='urgent', created_by=admin.id, is_active=True),
        ])

        # ___ Settings ___________________________________
        settings = [
            ('gate_closing_time', '21:00', 'Gate closing time'),
            ('curfew_time', '22:00', 'Curfew time'),
            ('max_monthly_outpasses', '8', 'Global monthly outpass limit'),
            ('college_name', 'National Institute of Technology', 'College name'),
        ]
        for key, val, desc in settings:
            Setting.set(key, val, desc)

        db.session.commit()
        print('[OK] Announcements and settings created')
        print()
        print('=' * 50)
        print('  SEED DATA COMPLETE')
        print('=' * 50)
        print()
        print('  Demo Login Credentials:')
        print('  _________________________')
        print('  Admin:     admin / Admin@123')
        print('  Warden:    warden1 / Warden@123')
        print('  Warden:    warden2 / Warden@123')
        print('  Advisor:   advisor1 / Advisor@123')
        print('  Guard:     guard1 / Guard@123')
        print('  Guard:     guard2 / Guard@123')
        print('  Students:  STU001-STU030 / Student@123')
        print()


if __name__ == '__main__':
    seed()
