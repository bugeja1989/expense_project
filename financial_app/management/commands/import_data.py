from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
from django.conf import settings
import csv
import pandas as pd
import logging
import os
from datetime import datetime

from financial_app.models import (
    Client, Invoice, InvoiceItem, 
    Expense, ExpenseCategory, Company
)

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Import data from CSV/Excel files'

    def add_arguments(self, parser):
        parser.add_argument(
            'file_path',
            type=str,
            help='Path to import file'
        )
        
        parser.add_argument(
            '--type',
            type=str,
            choices=['clients', 'invoices', 'expenses', 'categories'],
            required=True,
            help='Type of data to import'
        )
        
        parser.add_argument(
            '--company-id',
            type=int,
            required=True,
            help='Company ID to associate with imported data'
        )
        
        parser.add_argument(
            '--date-format',
            type=str,
            default='%Y-%m-%d',
            help='Date format in import file'
        )
        
        parser.add_argument(
            '--currency',
            type=str,
            default='EUR',
            help='Currency for monetary values'
        )
        
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Update existing records based on unique identifiers'
        )
        
        parser.add_argument(
            '--skip-errors',
            action='store_true',
            help='Continue import on error'
        )

    def handle(self, *args, **options):
        try:
            # Set up logging
            self.setup_logging()
            
            # Validate company
            company = self.get_company(options['company_id'])
            
            # Read import file
            data = self.read_import_file(
                options['file_path'],
                options['date_format']
            )
            
            # Process data based on type
            import_method = getattr(self, f"import_{options['type']}")
            stats = import_method(
                data,
                company,
                options['update_existing'],
                options['skip_errors'],
                options['currency']
            )
            
            # Log summary
            self.log_import_summary(stats, options['type'])
            
        except Exception as e:
            logger.error(f"Import failed: {str(e)}")
            raise CommandError(f"Import failed: {str(e)}")

    def setup_logging(self):
        """Configure logging for import process."""
        log_dir = os.path.join(settings.BASE_DIR, 'logs', 'imports')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        log_file = os.path.join(
            log_dir,
            f'import_{timezone.now().strftime("%Y%m%d_%H%M%S")}.log'
        )
        
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )

    def get_company(self, company_id):
        """Get and validate company."""
        try:
            return Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            raise CommandError(f"Company with ID {company_id} does not exist")

    def read_import_file(self, file_path, date_format):
        """Read and validate import file."""
        if not os.path.exists(file_path):
            raise CommandError(f"File not found: {file_path}")
            
        file_ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if file_ext == '.csv':
                return pd.read_csv(file_path)
            elif file_ext in ['.xlsx', '.xls']:
                return pd.read_excel(file_path)
            else:
                raise CommandError(f"Unsupported file type: {file_ext}")
        except Exception as e:
            raise CommandError(f"Error reading file: {str(e)}")

    @transaction.atomic
    def import_clients(self, data, company, update_existing, skip_errors, currency):
        """Import client data."""
        required_fields = ['name', 'email']
        self.validate_fields(data, required_fields)
        
        stats = {
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0
        }
        
        for _, row in data.iterrows():
            try:
                client_data = {
                    'name': row['name'],
                    'email': row['email'],
                    'phone': row.get('phone', ''),
                    'address': row.get('address', ''),
                    'vat_number': row.get('vat_number', ''),
                    'notes': row.get('notes', '')
                }
                
                if update_existing:
                    client, created = Client.objects.update_or_create(
                        company=company,
                        email=row['email'],
                        defaults=client_data
                    )
                else:
                    client = Client.objects.create(
                        company=company,
                        **client_data
                    )
                    created = True
                
                stats['processed'] += 1
                if created:
                    stats['created'] += 1
                else:
                    stats['updated'] += 1
                    
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"Error importing client: {str(e)}")
                if not skip_errors:
                    raise
        
        return stats

    @transaction.atomic
    def import_invoices(self, data, company, update_existing, skip_errors, currency):
        """Import invoice data."""
        required_fields = ['client_email', 'amount', 'issue_date', 'due_date']
        self.validate_fields(data, required_fields)
        
        stats = {
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0
        }
        
        for _, row in data.iterrows():
            try:
                # Get client
                client = Client.objects.get(
                    company=company,
                    email=row['client_email']
                )
                
                invoice_data = {
                    'company': company,
                    'client': client,
                    'issue_date': pd.to_datetime(row['issue_date']).date(),
                    'due_date': pd.to_datetime(row['due_date']).date(),
                    'total_amount': row['amount'],
                    'status': row.get('status', 'DRAFT'),
                    'notes': row.get('notes', '')
                }
                
                if update_existing and 'invoice_number' in row:
                    invoice, created = Invoice.objects.update_or_create(
                        company=company,
                        invoice_number=row['invoice_number'],
                        defaults=invoice_data
                    )
                else:
                    invoice = Invoice.objects.create(**invoice_data)
                    created = True
                
                # Import invoice items if present
                if 'items' in row:
                    self.import_invoice_items(invoice, row['items'])
                
                stats['processed'] += 1
                if created:
                    stats['created'] += 1
                else:
                    stats['updated'] += 1
                    
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"Error importing invoice: {str(e)}")
                if not skip_errors:
                    raise
        
        return stats

    def import_invoice_items(self, invoice, items_data):
        """Import invoice items."""
        items = []
        for item in items_data:
            items.append(InvoiceItem(
                invoice=invoice,
                description=item['description'],
                quantity=item['quantity'],
                unit_price=item['unit_price']
            ))
        InvoiceItem.objects.bulk_create(items)

    @transaction.atomic
    def import_expenses(self, data, company, update_existing, skip_errors, currency):
        """Import expense data."""
        required_fields = ['category', 'amount', 'date']
        self.validate_fields(data, required_fields)
        
        stats = {
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0
        }
        
        for _, row in data.iterrows():
            try:
                # Get or create category
                category, _ = ExpenseCategory.objects.get_or_create(
                    name=row['category']
                )
                
                expense_data = {
                    'company': company,
                    'category': category,
                    'amount': row['amount'],
                    'date': pd.to_datetime(row['date']).date(),
                    'description': row.get('description', ''),
                    'vendor': row.get('vendor', ''),
                    'reference_number': row.get('reference_number', ''),
                    'payment_method': row.get('payment_method', 'CASH'),
                    'tax_deductible': row.get('tax_deductible', False)
                }
                
                if update_existing and 'reference_number' in row:
                    expense, created = Expense.objects.update_or_create(
                        company=company,
                        reference_number=row['reference_number'],
                        defaults=expense_data
                    )
                else:
                    expense = Expense.objects.create(**expense_data)
                    created = True
                
                stats['processed'] += 1
                if created:
                    stats['created'] += 1
                else:
                    stats['updated'] += 1
                    
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"Error importing expense: {str(e)}")
                if not skip_errors:
                    raise
        
        return stats

    @transaction.atomic
    def import_categories(self, data, company, update_existing, skip_errors, currency):
        """Import expense categories."""
        required_fields = ['name']
        self.validate_fields(data, required_fields)
        
        stats = {
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0
        }
        
        for _, row in data.iterrows():
            try:
                category_data = {
                    'name': row['name'],
                    'description': row.get('description', ''),
                    'is_active': row.get('is_active', True)
                }
                
                if update_existing:
                    category, created = ExpenseCategory.objects.update_or_create(
                        name=row['name'],
                        defaults=category_data
                    )
                else:
                    category = ExpenseCategory.objects.create(**category_data)
                    created = True
                
                stats['processed'] += 1
                if created:
                    stats['created'] += 1
                else:
                    stats['updated'] += 1
                    
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"Error importing category: {str(e)}")
                if not skip_errors:
                    raise
        
        return stats

    def validate_fields(self, data, required_fields):
        """Validate required fields in import data."""
        missing_fields = set(required_fields) - set(data.columns)
        if missing_fields:
            raise CommandError(
                f"Missing required fields: {', '.join(missing_fields)}"
            )

    def log_import_summary(self, stats, import_type):
        """Log import summary."""
        summary = (
            f"\nImport Summary for {import_type}\n"
            f"------------------------\n"
            f"Records processed: {stats['processed']}\n"
            f"Records created: {stats['created']}\n"
            f"Records updated: {stats['updated']}\n"
            f"Errors encountered: {stats['errors']}\n"
        )
        
        self.stdout.write(self.style.SUCCESS(summary))
        logger.info(summary)