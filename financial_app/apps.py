from django.apps import AppConfig
from django.db.models.signals import post_migrate

class FinancialAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'financial_app'
    verbose_name = 'Financial Management'

    def ready(self):
        # Import signal handlers
        from . import signals
        
        # Register for activity stream
        from actstream import registry
        registry.register(self.get_model('Company'))
        registry.register(self.get_model('Client'))
        registry.register(self.get_model('Invoice'))
        registry.register(self.get_model('Expense'))
        
        # Create default expense categories
        post_migrate.connect(self.create_default_categories, sender=self)

    def create_default_categories(self, **kwargs):
        from .models import ExpenseCategory
        
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