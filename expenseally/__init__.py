from __future__ import absolute_import, unicode_literals

# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from .celery import app as celery_app

# Set the default Django settings module for Celery
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'expenseally.settings')

__all__ = ('celery_app',)

# Set version
__version__ = '1.0.0'

# Set app config
default_app_config = 'expenseally.apps.ExpenseallyConfig'

# Configure logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

# Set up Django app registry
def setup():
    """
    Setup function for the ExpenseAlly application.
    This is called when Django starts.
    """
    try:
        # Initialize Celery
        celery_app.autodiscover_tasks()
        
        # Log successful initialization
        logging.info('ExpenseAlly initialized successfully')
        
    except Exception as e:
        logging.error(f'Error initializing ExpenseAlly: {str(e)}')
        raise

# Setup signal handlers
from django.db.models.signals import post_migrate
from django.dispatch import receiver

@receiver(post_migrate)
def on_post_migrate(sender, **kwargs):
    """
    Signal handler for post-migrate signal.
    Used to perform any necessary setup after database migrations.
    """
    try:
        # Import models here to avoid circular imports
        from financial_app.models import ExpenseCategory
        
        # Create default expense categories if they don't exist
        default_categories = [
            ('UTILITIES', 'Utilities'),
            ('OFFICE', 'Office Supplies'),
            ('SALARY', 'Salary'),
            ('RENT', 'Rent'),
            ('MARKETING', 'Marketing'),
            ('TRAVEL', 'Travel'),
            ('OTHER', 'Other'),
        ]
        
        for category_id, name in default_categories:
            ExpenseCategory.objects.get_or_create(
                id=category_id,
                defaults={'name': name}
            )
            
        logging.info('Default expense categories created successfully')
        
    except Exception as e:
        logging.error(f'Error creating default expense categories: {str(e)}')

# Initialize application
setup()