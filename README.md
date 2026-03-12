## Early Development Screening System (Django)

Frontend + Django structure for an early diagnosis and monitoring system for child development delays.

### Quick start (Windows / PowerShell)

Create venv and install dependencies:

```bash
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
```

Run migrations and start server:

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

### Notes

- Survey questions are **not hardcoded**. Survey pages render from `questions` querysets (empty until you add records in admin / DB).
- Placeholder hero image reference: `static/img/family_with_child_placeholder.jpg` (replace with a real JPG later).
