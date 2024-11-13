from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from decimal import Decimal
import random
import faker
import logging
from datetime import timedelta

from financial_app.models import (
    Company, Client, Invoice, InvoiceItem,
    Expense, ExpenseCategory, UserProfile,
    PaymentRecord
)

logger = logging.getLogger(__name__)
fake = faker.Faker()

class Command(BaseCommand):
    help = 'Create test data for development and testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--users',
            type=int,
            default=5,
            help='Number of test users to create'
        )
        
        parser.add_argument(
            '--clients',
            type=int,
            default=20,
            help='Number of clients per company'
        )
        
        parser.add_argument(
            '--invoices',
            type=int,
            default=50,
            help='Number of invoices per company'
        )
        
        parser.add_argument(
            '--expenses',
            type=int,
            default=100,
            help='Number of expenses per company'
        )
        
        parser.add_argument(
            '--months',
            type=int,
            default=12,
            help='Number of months of historical data'
        )
        
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing test data before creating new'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            # Set up logging
            self.setup_logging()
            
            if options['clear']:
                self.clear_test_data()
            
            # Create test data
            users = self.create_test_users(options['users'])
            
            for user in users:
                company = self.create_test_company(user)
                self.create_test_categories()
                clients = self.create_test_clients(company, options['clients'])
                self.create_test_invoices(
                    company,
                    clients,
                    options['invoices'],
                    options['months']
                )
                self.create_test_expenses(
                    company,
                    options['expenses'],
                    options['months']
                )
            
            self.stdout.write(
                self.style.SUCCESS('Successfully created test data')
            )
            
        except Exception as e:
            logger.error(f"Test data creation failed: {str(e)}")
            raise CommandError(f"Test data creation failed: {str(e)}")

    def setup_logging(self):
        """Configure logging for test data creation."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )

    def clear_test_data(self):
        """Clear existing test data."""
        logger.info("Clearing existing test data...")
        
        # Only delete test users and their related data
        User.objects.filter(email__endswith='@example.com').delete()
        logger.info("Test data cleared")

    def create_test_users(self, count):
        """Create test users with profiles."""
        users = []
        
        for i in range(count):
            try:
                first_name = fake.first_name()
                last_name = fake.last_name()
                email = f"user{i}@example.com"
                
                user = User.objects.create_user(
                    username=f"testuser{i}",
                    email=email,
                    password="testpass123",
                    first_name=first_name,
                    last_name=last_name
                )
                
                # Create user profile
                UserProfile.objects.create(
                    user=user,
                    role=random.choice(['ADMIN', 'ACCOUNTANT', 'VIEWER']),
                    phone=fake.phone_number(),
                    notification_preferences={
                        'email': True,
                        'web': True
                    }
                )
                
                users.append(user)
                logger.info(f"Created test user: {user.username}")
                
            except Exception as e:
                logger.error(f"Error creating test user: {str(e)}")
                continue
        
        return users

    def create_test_company(self, user):
        """Create a test company for user."""
        company = Company.objects.create(
            name=fake.company(),
            owner=user,
            vat_number=f"VAT{fake.random_number(digits=8)}",
            registration_number=fake.random_number(digits=10),
            preferred_currency='EUR',
            address=fake.address(),
            phone=fake.phone_number(),
            email=fake.company_email(),
            website=fake.url(),
            tax_number=fake.random_number(digits=9)
        )
        
        logger.info(f"Created test company: {company.name}")
        return company

    def create_test_categories(self):
        """Create test expense categories."""
        categories = [
            'Rent', 'Utilities', 'Supplies', 'Advertising',
            'Insurance', 'Travel', 'Maintenance', 'Software',
            'Professional Services', 'Office Equipment'
        ]
        
        for name in categories:
            ExpenseCategory.objects.get_or_create(
                name=name,
                defaults={'description': f"Expenses related to {name.lower()}"}
            )
        
        logger.info("Created test expense categories")

    def create_test_clients(self, company, count):
        """Create test clients for company."""
        clients = []
        
        for _ in range(count):
            try:
                client = Client.objects.create(
                    company=company,
                    name=fake.company(),
                    email=fake.company_email(),
                    phone=fake.phone_number(),
                    address=fake.address(),
                    vat_number=f"VAT{fake.random_number(digits=8)}",
                    contact_person=fake.name(),
                    payment_terms=random.choice([7, 14, 30, 45, 60]),
                    credit_limit=Decimal(random.randint(5000, 50000))
                )
                
                clients.append(client)
                
            except Exception as e:
                logger.error(f"Error creating test client: {str(e)}")
                continue
        
        logger.info(f"Created {len(clients)} test clients")
        return clients

    def create_test_invoices(self, company, clients, count, months):
        """Create test invoices with items."""
        start_date = timezone.now().date() - timedelta(days=30*months)
        
        for _ in range(count):
            try:
                # Generate random date within range
                issue_date = start_date + timedelta(
                    days=random.randint(0, 30*months)
                )
                
                client = random.choice(clients)
                payment_terms = client.payment_terms or 30
                due_date = issue_date + timedelta(days=payment_terms)
                
                invoice = Invoice.objects.create(
                    company=company,
                    client=client,
                    issue_date=issue_date,
                    due_date=due_date,
                    status=self.get_random_invoice_status(issue_date, due_date),
                    tax_rate=Decimal('20.00'),
                    notes=fake.text()
                )
                
                # Create invoice items
                self.create_test_invoice_items(invoice)
                
                # Create payment records for paid invoices
                if invoice.status in ['PAID', 'PARTIALLY_PAID']:
                    self.create_test_payments(invoice)
                
            except Exception as e:
                logger.error(f"Error creating test invoice: {str(e)}")
                continue
        
        logger.info(f"Created {count} test invoices")

    def create_test_invoice_items(self, invoice):
        """Create test items for invoice."""
        num_items = random.randint(1, 5)
        
        for _ in range(num_items):
            InvoiceItem.objects.create(
                invoice=invoice,
                description=fake.sentence(),
                quantity=Decimal(random.randint(1, 10)),
                unit_price=Decimal(random.randint(100, 1000)),
                tax_rate=Decimal('20.00')
            )

    def create_test_payments(self, invoice):
        """Create test payment records for invoice."""
        if invoice.status == 'PAID':
            amount = invoice.total_amount
        else:
            amount = Decimal(random.uniform(0.4, 0.8)) * invoice.total_amount
        
        PaymentRecord.objects.create(
            invoice=invoice,
            amount=amount,
            payment_date=invoice.issue_date + timedelta(
                days=random.randint(0, 30)
            ),
            payment_method=random.choice([
                'BANK_TRANSFER', 'CREDIT_CARD', 'CASH'
            ]),
            status='COMPLETED',
            reference_number=f"PAY-{fake.random_number(digits=8)}",
            processed_by=invoice.company.owner
        )

    def create_test_expenses(self, company, count, months):
        """Create test expenses."""
        start_date = timezone.now().date() - timedelta(days=30*months)
        categories = list(ExpenseCategory.objects.all())
        
        for _ in range(count):
            try:
                expense_date = start_date + timedelta(
                    days=random.randint(0, 30*months)
                )
                
                Expense.objects.create(
                    company=company,
                    category=random.choice(categories),
                    amount=Decimal(random.randint(50, 5000)),
                    date=expense_date,
                    description=fake.text(),
                    vendor=fake.company(),
                    reference_number=f"EXP-{fake.random_number(digits=8)}",
                    payment_method=random.choice([
                        'CASH', 'BANK_TRANSFER', 'CREDIT_CARD'
                    ]),
                    tax_deductible=random.choice([True, False]),
                    created_by=company.owner
                )
                
            except Exception as e:
                logger.error(f"Error creating test expense: {str(e)}")
                continue
        
        logger.info(f"Created {count} test expenses")

    def get_random_invoice_status(self, issue_date, due_date):
        """Determine random invoice status based on dates."""
        today = timezone.now().date()
        
        if issue_date > today:
            return 'DRAFT'
        
        if due_date < today:
            return random.choice(['PAID', 'OVERDUE', 'PARTIALLY_PAID'])
        
        return random.choice(['DRAFT', 'SENT', 'PAID', 'PARTIALLY_PAID'])

    def generate_random_amount(self, min_amount, max_amount):
        """Generate random decimal amount."""
        amount = random.uniform(min_amount, max_amount)
        return Decimal(str(round(amount, 2)))