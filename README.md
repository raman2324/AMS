# AMS — Approval Management System

A Django-based approval workflow system for managing software subscriptions and one-off expense requests. Integrates with a companion CMS (HR Docs) to sync approved request records automatically.

---

## Tech Stack

- **Backend:** Django 5.x, django-fsm-2 (finite state machine for approval workflows)
- **Database:** MySQL 8.0 (shared with CMS on the same server)
- **Web server:** Gunicorn + Nginx
- **Auth:** django-allauth (email-based login)
- **Container:** Docker + Docker Compose

---

## Approval Workflow

```
Employee submits request
        ↓
Manager approves / rejects
        ↓
Finance executive approves / rejects
        ↓
(Subscriptions) IT provisions
        ↓
Active / Approved
```

C-suite employees (no manager) skip straight to Finance.

---

## Running with Docker

### Prerequisites
- Docker Desktop running
- A shared Docker network and MySQL instance started by the CMS project

### Step 1 — Start CMS first (creates shared MySQL + network)
```bash
cd path/to/CMS
docker compose up --build -d
```

### Step 2 — Start AMS
```bash
cd path/to/AMS
docker compose up --build -d
```

AMS is available at **http://localhost** (or your WSL2 IP on port 80).

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True` for development |
| `ALLOWED_HOSTS` | Comma-separated allowed hostnames / IPs |
| `DATABASE_URL` | `mysql://user:pass@shared_mysql:3306/ams_db` |
| `DEFAULT_FROM_EMAIL` | Sender address for email notifications |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins for CSRF |
| `DOCUMENT_ENCRYPTION_KEY` | Fernet key shared with CMS for file encryption |

---

## Database Architecture

Both AMS and CMS connect to the same MySQL 8.0 server (`shared_mysql`), each using a separate database:

```
shared_mysql (MySQL 8.0)
├── ams_db   ← AMS tables
└── cms_db   ← CMS tables
```

The `init-mysql.sql` file in the CMS project creates both databases on first boot and grants the shared user access to both.

---

## CMS Integration (Receipt Sync)

When an AMS request reaches final approval, it is automatically synced to the CMS uploads table so Finance can view it at `/uploads/` in CMS.

- If the request has a receipt file → the file is encrypted and copied to the shared volume
- If no receipt → a JSON approval summary is generated and synced instead

To retroactively sync all existing approved requests:
```bash
docker exec ams-web python manage.py sync_approvals_to_cms
```

---

## Shared Docker Volume

Receipt files are shared between AMS and CMS via a named Docker volume:

| Container | Mount path |
|---|---|
| AMS | `/app/media/shared_receipts` |
| CMS | `/app/local_pdfs/shared_receipts` |

Create the volume once before starting either service:
```bash
docker volume create ams_receipts_shared
```

---

## User Roles

| Role | Permissions |
|---|---|
| Employee | Submit requests |
| Manager | Approve / reject employee requests |
| Finance | Approve / reject after manager |
| IT | Provision approved subscriptions |
| Admin | Full access + Finance Head visibility |

---

## Management Commands

```bash
# Seed demo users and sample data
docker exec ams-web python manage.py seed_data

# Sync all approved requests to CMS uploads
docker exec ams-web python manage.py sync_approvals_to_cms

# Send renewal reminder emails
docker exec ams-web python manage.py send_renewal_reminders
```
