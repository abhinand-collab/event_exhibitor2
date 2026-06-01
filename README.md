# Exhibitor Event Management System

A robust Django-based system for managing event registrations, badge issuance, and bulk attendee invitations. This application features a non-blocking background processing architecture for handling large datasets and a live progress tracking dashboard.

## 🚀 Key Features

- **Dashboard Analytics:** Detailed breakdown of badge statistics (VIP, Exhibitor, Visitor) with live progress tracking.
- **Bulk Attendee Import:** Upload Excel/CSV files with custom column mapping and real-time validation.
- **Background Processing:** Celery-driven architecture ensures UI remains responsive during large imports.
- **Consolidated Registration:** Unified modal for creating and editing attendee details.
- **Invitation System:** Send bulk email invitations with unique tokens for attendee registration.
- **Audit Logging:** Comprehensive tracking of changes to attendees and badges using `django-auditlog`.
- **Duplicate Detection:** Automatic detection of duplicate emails within imports and against existing records.
- **Security:** Built-in locking mechanisms to prevent race conditions during concurrent bulk operations.

## 🛠 Tech Stack

- **Backend:** Django 6.0+, Python 3.x
- **Task Queue:** Celery with Redis as the Broker/Result Backend
- **Database:** PostgreSQL (configured for production-ready performance)
- **Frontend:** HTML5, CSS3 (Vanilla), JavaScript, jQuery, Bootstrap 5
- **Libraries:** Select2 (flags support), intl-tel-input (phone validation), SheetJS (XLSX parsing)

## ⚙️ Project Setup

### 1. Prerequisites
- Python 3.8+
- Redis Server (Running on `127.0.0.1:6379`)
- PostgreSQL Server

### 2. Installation
Clone the repository and set up a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Database Setup
Ensure you have a PostgreSQL database named `exhibitor_db` and a user `exhibito_admin` as per `settings.py`.

Apply migrations and create a superuser:
```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Background Worker Setup (Celery)
The project uses two separate queues to ensure that slow email delivery doesn't block management tasks.

**Important for Windows Users:**
1. Use `python -m celery` to avoid "Fatal error in launcher" issues.
2. **ALWAYS** include `-P solo` (pool: solo) in your worker commands. Windows does not support Celery's default 'prefork' pool, and omitting it will cause errors in `billiard/pool.py`.

#### Running All Queues Together (Development)
In a separate terminal:
```bash
# Windows
python -m celery -A event_exhibitor worker --loglevel=info -P solo

# Linux/Mac
python -m celery -A event_exhibitor worker --loglevel=info
```

#### Running Specific Queues (Production Recommended)
To separate "fast" management tasks from "slow" email tasks, run two worker instances:

**Worker 1: Management Tasks (default queue)**
```bash
# Windows
python -m celery -A event_exhibitor worker -Q default --loglevel=info -P solo -n worker_mgmt@%h

# Linux/Mac
python -m celery -A event_exhibitor worker -Q default --loglevel=info -n worker_mgmt@%h
```

**Worker 2: Email Tasks (emails queue)**
```bash
# Windows
python -m celery -A event_exhibitor worker -Q emails --loglevel=info -P solo -n worker_emails@%h

# Linux/Mac
python -m celery -A event_exhibitor worker -Q emails --loglevel=info -n worker_emails@%h
```

#### Scheduled Tasks (Celery Beat)
To enable scheduled tasks (like automatic reminders at the top of every hour):
```bash
python -m celery -A event_exhibitor beat --loglevel=info
```

### 5. Running the Application
```bash
python manage.py runserver
```
Access the application at `http://127.0.0.1:8000`

## 📧 Configuration

The project is pre-configured to use Gmail SMTP for sending emails. Update the following in `event_exhibitor/settings.py` for your environment:

- `EMAIL_HOST_USER`: Your email address
- `EMAIL_HOST_PASSWORD`: Your App-specific password
- `CELERY_BROKER_URL`: Redis connection string
- `DATABASES`: Update PostgreSQL credentials if different.

## 📁 Project Structure

- `/exhibitor`: Core application logic (Views, Tasks, Models)
- `/exhibitor/templates/includes`: Reusable components (Bulk Upload, Consolidated Modal, Invitations)
- `/exhibitor/utils`: Utility functions for Redis locking and Email services
- `/static`: Project assets (CSS, Styles, Sample Templates)
