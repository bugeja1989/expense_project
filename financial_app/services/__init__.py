from .invoice_service import InvoiceService
from .expense_service import ExpenseService
from .report_service import ReportService
from .analytics_service import AnalyticsService
from .client_service import ClientService

__all__ = [
    'InvoiceService',
    'ExpenseService',
    'ReportService',
    'AnalyticsService',
    'ClientService'
]

# Service Registry for dependency injection
class ServiceRegistry:
    """
    Registry for all application services to facilitate dependency injection
    and service management.
    """
    _instance = None
    _services = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ServiceRegistry, cls).__new__(cls)
            # Initialize default services
            cls._instance._services = {
                'invoice': InvoiceService,
                'expense': ExpenseService,
                'report': ReportService,
                'analytics': AnalyticsService,
                'client': ClientService
            }
        return cls._instance

    @classmethod
    def get_service(cls, service_name):
        """
        Get a service instance by name.
        """
        instance = cls()
        service = instance._services.get(service_name)
        if not service:
            raise ValueError(f"Service {service_name} not found")
        return service

    @classmethod
    def register_service(cls, name, service_class):
        """
        Register a new service or override existing one.
        """
        instance = cls()
        instance._services[name] = service_class

# Service Factory for creating service instances
class ServiceFactory:
    """
    Factory class for creating service instances with proper initialization.
    """
    @staticmethod
    def create_invoice_service():
        return InvoiceService()

    @staticmethod
    def create_expense_service():
        return ExpenseService()

    @staticmethod
    def create_report_service():
        return ReportService()

    @staticmethod
    def create_analytics_service():
        return AnalyticsService()

    @staticmethod
    def create_client_service():
        return ClientService()

# Service Context Manager for transaction handling
class ServiceContext:
    """
    Context manager for handling service operations within transactions.
    """
    def __init__(self, service):
        self.service = service
        self.error = None

    def __enter__(self):
        return self.service

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Log error and handle cleanup if needed
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in service operation: {exc_val}")
            self.error = exc_val
            return False  # Re-raise the exception
        return True

# Utility functions for service operations
def get_service(service_name):
    """
    Utility function to get a service instance with context management.
    Usage:
        with get_service('invoice') as invoice_service:
            invoice_service.create_invoice(...)
    """
    service_class = ServiceRegistry.get_service(service_name)
    return ServiceContext(service_class())

# Service Decorators
def handle_service_errors(func):
    """
    Decorator to handle common service errors and logging.
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Service error in {func.__name__}: {str(e)}")
            raise
    return wrapper

def require_transaction(func):
    """
    Decorator to ensure operation is executed within a transaction.
    """
    from django.db import transaction
    def wrapper(*args, **kwargs):
        with transaction.atomic():
            return func(*args, **kwargs)
    return wrapper

# Service Events
class ServiceEvent:
    """
    Base class for service events for event-driven operations.
    """
    def __init__(self, event_type, data):
        self.event_type = event_type
        self.data = data
        self.timestamp = import_datetime.now()

    def __str__(self):
        return f"{self.event_type} at {self.timestamp}"

# Initialize services on module load
ServiceRegistry()