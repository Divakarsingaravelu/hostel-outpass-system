# 🏫 Digital Hostel Outpass Management System

A production-quality web application that replaces paper-based hostel outpass processes. Students request outpasses online, wardens approve them, and security guards verify students at the gate using QR codes.

## 🚀 Quick Start

```bash
# 1. Clone and enter the directory
cd hostel-outpass

# 2. Install dependencies
pip install -r requirements.txt

# 3. Seed the database with demo data
python seed.py

# 4. Run the application
flask run
# or
python run.py
```

Open **http://localhost:5000** in your browser.

## 🔑 Demo Credentials

| Role | Username | Password | Notes |
|------|----------|----------|-------|
| **Admin** | `admin` | `Admin@123` | Full system access |
| **Warden** | `warden1` | `Warden@123` | Boys Hostel 1 |
| **Warden** | `warden2` | `Warden@123` | Boys Hostel 2 |
| **Advisor** | `advisor1` | `Advisor@123` | CSE Department |
| **Guard** | `guard1` | `Guard@123` | Gate scanner |
| **Guard** | `guard2` | `Guard@123` | Gate scanner |
| **Student** | `STU001` - `STU030` | `Student@123` | 30 students with profiles |

## 📁 Project Structure

```
hostel-outpass/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── models/              # SQLAlchemy models (User, Student, Outpass, etc.)
│   ├── routes/              # Blueprint routes (auth, student, warden, guard, admin, api)
│   ├── services/            # Business logic (outpass, notification, QR, PDF, audit)
│   ├── templates/           # Jinja2 templates organized by role
│   ├── static/              # CSS, JS, uploads
│   └── utils/               # Decorators, validators
├── tests/                   # pytest test suite
├── config.py                # Environment-based configuration
├── seed.py                  # Database seeder with demo data
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── run.py                   # Application entry point
└── README.md
```

## 🔧 Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key | `dev-secret-key` |
| `DATABASE_URL` | Database URI (PostgreSQL) | SQLite |
| `QR_SIGNING_SECRET` | QR code signing key | `qr-dev-secret` |
| `MAIL_SERVER` | SMTP server | Console output |
| `MAIL_USERNAME` | SMTP username | (empty = console) |
| `LOCKOUT_THRESHOLD` | Failed login attempts before lockout | `5` |
| `LOCKOUT_DURATION_MINUTES` | Lockout duration | `15` |

## 👤 User Roles

### Student
- Apply for outpass (Local, Late Night, Weekend, Emergency, Medical, Vacation)
- View status timeline, download PDF with QR code
- Cancel pending requests, view history

### Warden
- Review and approve/reject requests with remarks
- Bulk approve, emergency fast-track
- View students in block, currently outside list

### Class Advisor / HOD
- First-level approval for Vacation/Long Leave types
- Configurable approval chain per outpass type

### Security Guard
- Scan QR code (camera) or enter outpass number
- Mark OUT / Mark IN with timestamps
- Detect late returns, view movement log

### Admin
- Manage users (CRUD + CSV import), blocks, rooms, departments
- Configure outpass types and approval chains
- Student restrictions (disciplinary block)
- Reports & analytics (Chart.js), Excel export
- Audit log viewer, announcements

## 🔒 Security

- **CSRF** protection on all forms (Flask-WTF)
- **Password hashing** with werkzeug
- **Account lockout** after failed attempts
- **Rate limiting** on login endpoints
- **Signed QR codes** with itsdangerous (tamper-proof, expiring)
- **Secure file uploads** (extension/MIME check, random filenames)
- **Security headers** (X-Frame-Options, X-Content-Type-Options, etc.)
- **Server-side validation** for all inputs
- **Audit logging** for all significant actions

## 📊 REST API

Base URL: `/api/v1/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/login` | Login, returns user info |
| GET | `/api/v1/outpasses` | List outpasses (filtered by role) |
| POST | `/api/v1/outpasses` | Create outpass request |
| GET | `/api/v1/outpasses/<id>` | Get outpass details |
| POST | `/api/v1/approvals/<id>` | Approve/reject outpass |
| POST | `/api/v1/gate/verify` | Verify QR or outpass number |
| POST | `/api/v1/gate/mark` | Mark OUT or IN |

### Response Format
```json
{
    "success": true,
    "message": "OK",
    "data": { ... }
}
```

### Error Format
```json
{
    "success": false,
    "error": "Error message"
}
```

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=term-missing
```

## 🚀 Enterprise Deployment

The system is configured for cloud-native deployment with `gunicorn`, `whitenoise`, and `psycopg2-binary` for scalable production hosting.

### Option 1: Docker (Recommended)
We include a `Dockerfile` and `docker-compose.yml` pre-configured with PostgreSQL.

```bash
# Start the full stack (Flask + PostgreSQL)
docker-compose up -d --build
```
The app will be available at `http://localhost:5000`.

### Option 2: Heroku / Render / Railway
The repository includes a `Procfile` and `runtime.txt` for immediate PaaS deployment.

1. Connect your GitHub repository to Render/Railway.
2. Set the following environment variables:
   - `DATABASE_URL` (Your managed PostgreSQL URL)
   - `FLASK_ENV=production`
   - `SECRET_KEY` & `QR_SIGNING_SECRET`
3. The platform will automatically detect the `Procfile` and use `gunicorn run:app` to serve the app with `whitenoise` handling static files.

## 📋 Feature Checklist

| Feature | Status |
|---------|--------|
| Login with register/staff ID | ✅ Done |
| Password hashing | ✅ Done |
| First-login password change | ✅ Done |
| Forgot/reset password | ✅ Done |
| Account lockout | ✅ Done |
| Role-based access (@role_required) | ✅ Done |
| Student dashboard & profile | ✅ Done |
| Apply outpass with validation | ✅ Done |
| Outpass type rules & limits | ✅ Done |
| Overlap detection | ✅ Done |
| Configurable approval chain | ✅ Done |
| Warden approve/reject with remarks | ✅ Done |
| Bulk approve | ✅ Done |
| Emergency fast-track | ✅ Done |
| Parent confirmation (simulated) | ✅ Done |
| Auto-expiry | ✅ Done |
| QR code generation (signed) | ✅ Done |
| PDF outpass download | ✅ Done |
| Gate scanner (camera + manual) | ✅ Done |
| Mark OUT / Mark IN | ✅ Done |
| Overdue detection & alerts | ✅ Done |
| Admin CRUD (users, blocks, rooms) | ✅ Done |
| CSV bulk import | ✅ Done |
| Student restrictions | ✅ Done |
| In-app notifications | ✅ Done |
| Email abstraction (console dev) | ✅ Done |
| Reports & Chart.js analytics | ✅ Done |
| Excel export | ✅ Done |
| Audit log | ✅ Done |
| Announcements | ✅ Done |
| REST API (/api/v1/) | ✅ Done |
| Error pages (403, 404, 500) | ✅ Done |
| Responsive design | ✅ Done |
| CSRF protection | ✅ Done |
| Rate limiting | ✅ Done |
| Security headers | ✅ Done |
| pytest suite | ✅ Done |
| Seed data (30 students, 60 outpasses) | ✅ Done |

## 📝 License

MIT License — Built for educational purposes.
