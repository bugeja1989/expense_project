import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'expenseally.settings')

app = Celery('expenseally')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Configure periodic tasks
app.conf.beat_schedule = {
    'check-overdue-invoices': {
        'task': 'financial_app.tasks.check_overdue_invoices',
        'schedule': crontab(hour='*/1'),  # Run every hour
    },
    'send-daily-summary': {
        'task': 'financial_app.tasks.send_daily_summary',
        'schedule': crontab(hour=18, minute=0),  # Run at 6 PM daily
    },
    'backup-database': {
        'task': 'financial_app.tasks.backup_database',
        'schedule': crontab(hour=0, minute=0),  # Run at midnight
    },
}