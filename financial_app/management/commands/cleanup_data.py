from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.conf import settings
from django.db.models import Q
from django.core.files.storage import default_storage
import os
import logging
from datetime import timedelta

from financial_app.models import (
    Invoice, Expense, PaymentRecord, 
    Client, UserProfile, Company
)

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up old temporary files and archived data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        
        parser.add_argument(
            '--archive',
            action='store_true',
            help='Archive data instead of deleting'
        )
        
        parser.add_argument(
            '--days',
            type=int,
            default=90,
            help='Number of days to keep data'
        )
        
        parser.add_argument(
            '--types',
            nargs='+',
            choices=['temp_files', 'old_invoices', 'old_expenses', 
                    'inactive_clients', 'orphaned_files'],
            default=['temp_files', 'orphaned_files'],
            help='Types of data to clean up'
        )

    def handle(self, *args, **options):
        try:
            # Set up logging
            self.setup_logging()
            
            dry_run = options['dry_run']
            archive = options['archive']
            days = options['days']
            cleanup_types = options['types']
            
            stats = {
                'temp_files_cleaned': 0,
                'old_invoices_cleaned': 0,
                'old_expenses_cleaned': 0,
                'inactive_clients_cleaned': 0,
                'orphaned_files_cleaned': 0,
                'space_freed': 0
            }
            
            self.stdout.write(f"Starting cleanup process (Dry run: {dry_run})")
            
            # Process each cleanup type
            for cleanup_type in cleanup_types:
                try:
                    method = getattr(self, f'cleanup_{cleanup_type}')
                    type_stats = method(days, dry_run, archive)
                    
                    for key, value in type_stats.items():
                        stats[key] += value
                        
                except Exception as e:
                    logger.error(f"Error in {cleanup_type} cleanup: {str(e)}")
                    continue
            
            # Log summary
            self.log_summary(stats, dry_run)
            
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")
            raise CommandError(f"Cleanup failed: {str(e)}")

    def setup_logging(self):
        """Configure logging for the command."""
        log_dir = os.path.join(settings.BASE_DIR, 'logs', 'cleanup')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        log_file = os.path.join(
            log_dir,
            f'cleanup_{timezone.now().strftime("%Y%m%d")}.log'
        )
        
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )

    def cleanup_temp_files(self, days, dry_run=False, archive=False):
        """Clean up temporary files older than specified days."""
        stats = {
            'temp_files_cleaned': 0,
            'space_freed': 0
        }
        
        temp_dirs = [
            os.path.join(settings.MEDIA_ROOT, 'temp'),
            os.path.join(settings.MEDIA_ROOT, 'exports'),
            os.path.join(settings.MEDIA_ROOT, 'cache')
        ]
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        for temp_dir in temp_dirs:
            if not os.path.exists(temp_dir):
                continue
                
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    file_time = timezone.datetime.fromtimestamp(
                        os.path.getmtime(file_path)
                    )
                    
                    if timezone.make_aware(file_time) < cutoff_date:
                        stats['space_freed'] += os.path.getsize(file_path)
                        
                        if not dry_run:
                            if archive:
                                self.archive_file(file_path)
                            os.remove(file_path)
                            
                        stats['temp_files_cleaned'] += 1
                        logger.info(f"Cleaned temp file: {file_path}")
        
        return stats

    def cleanup_old_invoices(self, days, dry_run=False, archive=False):
        """Archive or delete old, paid invoices."""
        stats = {
            'old_invoices_cleaned': 0,
            'space_freed': 0
        }
        
        cutoff_date = timezone.now().date() - timedelta(days=days)
        
        old_invoices = Invoice.objects.filter(
            status='PAID',
            issue_date__lt=cutoff_date
        )
        
        for invoice in old_invoices:
            try:
                if not dry_run:
                    if archive:
                        self.archive_invoice(invoice)
                    else:
                        invoice.delete()
                        
                stats['old_invoices_cleaned'] += 1
                logger.info(f"Cleaned invoice: {invoice.invoice_number}")
                
            except Exception as e:
                logger.error(f"Error cleaning invoice {invoice.id}: {str(e)}")
                continue
        
        return stats

    def cleanup_old_expenses(self, days, dry_run=False, archive=False):
        """Archive or delete old expenses."""
        stats = {
            'old_expenses_cleaned': 0,
            'space_freed': 0
        }
        
        cutoff_date = timezone.now().date() - timedelta(days=days)
        
        old_expenses = Expense.objects.filter(
            date__lt=cutoff_date
        )
        
        for expense in old_expenses:
            try:
                if expense.receipt:
                    stats['space_freed'] += expense.receipt.size
                
                if not dry_run:
                    if archive:
                        self.archive_expense(expense)
                    else:
                        expense.delete()
                        
                stats['old_expenses_cleaned'] += 1
                logger.info(f"Cleaned expense: {expense.id}")
                
            except Exception as e:
                logger.error(f"Error cleaning expense {expense.id}: {str(e)}")
                continue
        
        return stats

    def cleanup_inactive_clients(self, days, dry_run=False, archive=False):
        """Clean up inactive clients with no recent activity."""
        stats = {
            'inactive_clients_cleaned': 0,
            'space_freed': 0
        }
        
        cutoff_date = timezone.now().date() - timedelta(days=days)
        
        inactive_clients = Client.objects.filter(
            is_active=False,
            updated_at__lt=cutoff_date
        ).exclude(
            invoices__issue_date__gte=cutoff_date
        )
        
        for client in inactive_clients:
            try:
                if not dry_run:
                    if archive:
                        self.archive_client(client)
                    else:
                        client.delete()
                        
                stats['inactive_clients_cleaned'] += 1
                logger.info(f"Cleaned client: {client.id}")
                
            except Exception as e:
                logger.error(f"Error cleaning client {client.id}: {str(e)}")
                continue
        
        return stats

    def cleanup_orphaned_files(self, days, dry_run=False, archive=False):
        """Clean up orphaned files in media directory."""
        stats = {
            'orphaned_files_cleaned': 0,
            'space_freed': 0
        }
        
        # Get all file fields from models
        file_fields = {
            'company_logos': Company.objects.values_list('logo', flat=True),
            'expense_receipts': Expense.objects.values_list('receipt', flat=True),
            'user_avatars': UserProfile.objects.values_list('avatar', flat=True)
        }
        
        # Get list of all files in media directory
        media_files = set()
        for root, dirs, files in os.walk(settings.MEDIA_ROOT):
            for file in files:
                media_files.add(os.path.join(root, file))
        
        # Get list of all files referenced in database
        db_files = set()
        for files in file_fields.values():
            for file in files:
                if file:
                    db_files.add(os.path.join(settings.MEDIA_ROOT, file))
        
        # Find orphaned files
        orphaned_files = media_files - db_files
        
        # Clean up orphaned files
        for file_path in orphaned_files:
            try:
                stats['space_freed'] += os.path.getsize(file_path)
                
                if not dry_run:
                    if archive:
                        self.archive_file(file_path)
                    os.remove(file_path)
                    
                stats['orphaned_files_cleaned'] += 1
                logger.info(f"Cleaned orphaned file: {file_path}")
                
            except Exception as e:
                logger.error(f"Error cleaning file {file_path}: {str(e)}")
                continue
        
        return stats

    def archive_file(self, file_path):
        """Archive a file to the archive directory."""
        archive_dir = os.path.join(settings.MEDIA_ROOT, 'archive')
        if not os.path.exists(archive_dir):
            os.makedirs(archive_dir)
            
        archive_path = os.path.join(
            archive_dir,
            f"{timezone.now().strftime('%Y%m%d')}_{os.path.basename(file_path)}"
        )
        
        os.rename(file_path, archive_path)
        logger.info(f"Archived file: {file_path} -> {archive_path}")

    def archive_invoice(self, invoice):
        """Archive invoice data."""
        # Implementation for invoice archiving
        pass

    def archive_expense(self, expense):
        """Archive expense data."""
        # Implementation for expense archiving
        pass

    def archive_client(self, client):
        """Archive client data."""
        # Implementation for client archiving
        pass

    def log_summary(self, stats, dry_run):
        """Log cleanup summary."""
        summary = (
            f"\nCleanup Summary (Dry Run: {dry_run})\n"
            f"--------------------------------\n"
            f"Temporary files cleaned: {stats['temp_files_cleaned']}\n"
            f"Old invoices cleaned: {stats['old_invoices_cleaned']}\n"
            f"Old expenses cleaned: {stats['old_expenses_cleaned']}\n"
            f"Inactive clients cleaned: {stats['inactive_clients_cleaned']}\n"
            f"Orphaned files cleaned: {stats['orphaned_files_cleaned']}\n"
            f"Total space freed: {self.format_size(stats['space_freed'])}\n"
        )
        
        self.stdout.write(self.style.SUCCESS(summary))
        logger.info(summary)

    def format_size(self, size):
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"