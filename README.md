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
- **Database:** SQLite (configured with WAL mode for performance)
- **Frontend:** HTML5, CSS3 (Vanilla), JavaScript, jQuery, Bootstrap 5
- **Libraries:** Select2 (flags support), intl-tel-input (phone validation), SheetJS (XLSX parsing)

## ⚙️ Project Setup

### 1. Prerequisites
- Python 3.8+
- Redis Server (Running on `127.0.0.1:6379`)

### 2. Installation
Clone the repository and set up a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Database Setup
Apply migrations and create a superuser:
```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Background Worker Setup
In a separate terminal, start the Celery worker to handle bulk imports and emails:
```bash
# Windows
celery -A event_exhibitor worker --loglevel=info -P solo

# Linux/Mac
celery -A event_exhibitor worker --loglevel=info
```

To enable scheduled tasks (like automatic reminders):
```bash
celery -A event_exhibitor beat --loglevel=info
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

## 📁 Project Structure

- `/exhibitor`: Core application logic (Views, Tasks, Models)
- `/exhibitor/templates/includes`: Reusable components (Bulk Upload, Consolidated Modal, Invitations)
- `/exhibitor/utils`: Utility functions for Redis locking and Email services
- `/static`: Project assets (CSS, Styles, Sample Templates)

