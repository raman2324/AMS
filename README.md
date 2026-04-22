# AMS — Approval Management System

A Django-based approval workflow system for managing software subscriptions and one-off expense requests within an organisation.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 5.x |
| Workflow | django-fsm-2 (finite state machine) |
| Database | MySQL 8.0 (own independent container) |
| Auth | django-allauth (email + password) |
| Frontend | Tailwind CSS, HTMX |
| Web server | Gunicorn + Nginx |
| Container | Docker + Docker Compose |

---

## Approval Workflow

```
Employee submits request
        ↓
Manager approves / rejects
        ↓
Finance executive approves / rejects
        ↓
[Subscriptions only] IT provisions
        ↓
Active (subscription) / Approved (expense)
```

**Request types:**
- **Subscription** — recurring SaaS tool or software licence (monthly / annual)
- **One-off Expense** — single purchase, conference ticket, equipment, etc.

---

## User Roles

| Role | What they can do |
|---|---|
| **Employee** | Submit requests, track their own requests |
| **Manager** | Approve or reject requests from direct reports |
| **Finance** | Approve or reject after manager; handle renewals |
| **IT** | Provision approved subscriptions (set account ID + billing start) |
| **HR** | View requests; offboard employees |
| **Admin** | Full access across all roles |

---

## Demo Accounts

All demo accounts use the password: **`password123`**

| Email | Role |
|---|---|
| admin@bv.com | Admin (superuser) |
| frank@bv.com | Admin (Finance Head) |
| carol@bv.com | Finance |
| mike@bv.com | Finance |
| dave@bv.com | IT |
| eve@bv.com | HR |
| bob@bv.com | Manager |
| sarah@bv.com | Manager |
| raj@bv.com | Manager |
| alice@bv.com | Employee (reports to Bob) |
| john@bv.com | Employee (reports to Bob) |
| priya@bv.com | Employee (reports to Sarah) |
| george@bv.com | Employee (reports to Bob) |

---

## Running with Docker

### Prerequisites
- Docker Desktop installed and running

### Start AMS

```bash
cd path/to/AMS
docker compose up --build -d
```

AMS spins up three containers:
- `ams-db-1` — MySQL 8.0 database (internal, not exposed)
- `ams-web` — Django + Gunicorn application
- `ams-nginx-1` — Nginx reverse proxy

App is available at **http://localhost** (or your machine IP on port 80).

### Stop AMS

```bash
docker compose down
```

---

## Environment Variables (`.env`)

| Variable | Description | Example |
|---|---|---|
| `SECRET_KEY` | Django secret key | `your-secret-key` |
| `DEBUG` | Enable debug mode | `True` |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts | `localhost,127.0.0.1` |
| `DATABASE_URL` | MySQL connection string | `mysql://admin:secret@db:3306/ams_db` |
| `DEFAULT_FROM_EMAIL` | Email sender address | `noreply@company.com` |
| `CSRF_TRUSTED_ORIGINS` | Trusted origins for CSRF | `http://localhost` |
| `DOCUMENT_ENCRYPTION_KEY` | Fernet key for file encryption | _(generate with cryptography)_ |

---

## Project Structure

```
AMS/
├── accounts/          # Custom user model, roles, login
├── approvals/         # Core approval workflow (FSM), request model
├── subscriptions/     # Subscription dashboard and renewal tracking
├── expenses/          # Expense list and submission
├── audit/             # Audit log, activity tracking, offboarding
├── notifications/     # Email notification handlers
├── management/        # Shared management commands
├── templates/         # All HTML templates (Tailwind CSS)
│   ├── approvals/
│   │   └── partials/  # HTMX partial templates
│   ├── subscriptions/
│   └── expenses/
├── nginx/             # Nginx config
├── ams/               # Django project settings (base / prod)
├── docker-compose.yml
├── Dockerfile
└── entrypoint.sh      # Runs migrations + seed + collectstatic on startup
```

---

## Key Pages

| URL | Description | Roles |
|---|---|---|
| `/requests/new/` | Submit a new request | All |
| `/requests/my/` | View your own requests with approval progress | All |
| `/requests/<id>/` | Request detail + approval actions | All with access |
| `/requests/inbox/` | Pending approvals queue | Manager, Finance, IT, Admin |
| `/subscriptions/` | Subscription dashboard (active, renewing, terminated) | All |
| `/expenses/` | Expense list grouped by state | All |
| `/admin-ams/my-audit/` | Personal activity log | All |
| `/admin-ams/audit/` | Full organisation audit log | Finance, Admin |
| `/admin-ams/offboard/` | Offboard an employee | HR, Admin |

---

## Request States

```
pending_manager → pending_finance → provisioning → active        (subscription)
pending_manager → pending_finance → approved                      (expense)
pending_manager → rejected_manager
pending_finance → rejected_finance
active → active_pending_renewal → renewing → active              (renewal)
active / renewing / provisioning → terminated
```

---

## Management Commands

```bash
# Seed demo users and sample data (runs automatically on container start)
docker exec ams-web python manage.py seed_data

# Send renewal reminder emails for expiring subscriptions
docker exec ams-web python manage.py send_renewal_reminders
```

---

## Running Locally (without Docker)

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment (uses SQLite by default if DATABASE_URL is not set)
cp .env .env.local   # edit as needed

# Apply migrations
python manage.py migrate

# Seed demo data
python manage.py seed_data

# Start dev server
python manage.py runserver
```

App will be available at **http://127.0.0.1:8000**.

---

## Architecture Notes

- **AMS and CMS are fully independent.** Each runs its own MySQL container with its own database. They share no network, no volume, and no database.
- **Approval state is managed via FSM.** The `ApprovalRequest.state` field transitions are enforced by `django-fsm-2` — invalid transitions raise exceptions rather than silently corrupting state.
- **Email notifications** are sent via Django's email backend (console in dev, SMTP in prod). Notifications fire on submit, approval, rejection, and renewal.
- **Nginx** serves static files directly and proxies all other requests to Gunicorn.
