from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.conf import settings
from django.db.models import Q, Sum
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
import logging
from datetime import datetime, timedelta

from financial_app.models import Invoice, Client, Company
from financial_app.services.invoice_service import InvoiceService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Send automated reminders for overdue invoices and upcoming payments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without sending actual emails'
        )
        
        parser.add_argument(
            '--company-id',
            type=int,
            help='Process reminders for specific company'
        )
        
        parser.add_argument(
            '--days-overdue',
            type=int,
            default=1,
            help='Minimum days overdue to send reminder'
        )
        
        parser.add_argument(
            '--days-before-due',
            type=int,
            default=3,
            help='Days before due date to send upcoming payment reminder'
        )
        
        parser.add_argument(
            '--reminder-type',
            type=str,
            choices=['overdue', 'upcoming', 'all'],
            default='all',
            help='Type of reminders to send'
        )

    def handle(self, *args, **options):
        try:
            # Set up logging
            self.setup_logging()
            
            # Get companies to process
            companies = self.get_companies(options.get('company_id'))
            
            total_sent = 0
            total_errors = 0
            
            self.stdout.write(f"Processing reminders for {len(companies)} companies")
            
            for company in companies:
                try:
                    sent, errors = self.process_company_reminders(company, options)
                    total_sent += sent
                    total_errors += errors
                except Exception as e:
                    logger.error(f"Error processing company {company.id}: {str(e)}")
                    total_errors += 1
                    continue
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully sent {total_sent} reminders with {total_errors} errors"
                )
            )
            
        except Exception as e:
            logger.error(f"Reminder sending failed: {str(e)}")
            raise CommandError(f"Reminder sending failed: {str(e)}")

    def setup_logging(self):
        """Configure logging for the command."""
        log_dir = os.path.join(settings.BASE_DIR, 'logs', 'reminders')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        log_file = os.path.join(
            log_dir,
            f'reminders_{timezone.now().strftime("%Y%m%d")}.log'
        )
        
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )

    def get_companies(self, company_id=None):
        """Get companies to process."""
        if company_id:
            return Company.objects.filter(id=company_id)
        return Company.objects.filter(is_active=True)

    def process_company_reminders(self, company, options):
        """Process reminders for a single company."""
        sent_count = 0
        error_count = 0
        
        reminder_type = options['reminder_type']
        dry_run = options['dry_run']
        
        if reminder_type in ['overdue', 'all']:
            # Process overdue invoices
            overdue_invoices = self.get_overdue_invoices(
                company,
                options['days_overdue']
            )
            
            for invoice in overdue_invoices:
                try:
                    if self.should_send_reminder(invoice):
                        if not dry_run:
                            self.send_overdue_reminder(invoice)
                        sent_count += 1
                        logger.info(f"Sent overdue reminder for invoice {invoice.id}")
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error sending overdue reminder for invoice {invoice.id}: {str(e)}")
        
        if reminder_type in ['upcoming', 'all']:
            # Process upcoming payments
            upcoming_invoices = self.get_upcoming_invoices(
                company,
                options['days_before_due']
            )
            
            for invoice in upcoming_invoices:
                try:
                    if not dry_run:
                        self.send_upcoming_reminder(invoice)
                    sent_count += 1
                    logger.info(f"Sent upcoming payment reminder for invoice {invoice.id}")
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error sending upcoming reminder for invoice {invoice.id}: {str(e)}")
        
        return sent_count, error_count

    def get_overdue_invoices(self, company, days_overdue):
        """Get overdue invoices that need reminders."""
        overdue_date = timezone.now().date() - timedelta(days=days_overdue)
        
        return Invoice.objects.filter(
            company=company,
            status__in=['SENT', 'PARTIALLY_PAID'],
            due_date__lte=overdue_date
        ).select_related('client')

    def get_upcoming_invoices(self, company, days_before):
        """Get upcoming invoices that need reminders."""
        target_date = timezone.now().date() + timedelta(days=days_before)
        
        return Invoice.objects.filter(
            company=company,
            status__in=['SENT', 'PARTIALLY_PAID'],
            due_date=target_date
        ).select_related('client')

    def should_send_reminder(self, invoice):
        """Check if reminder should be sent based on previous reminders."""
        if not invoice.last_reminder_sent:
            return True
            
        days_since_last = (timezone.now().date() - invoice.last_reminder_sent.date()).days
        
        # Determine reminder frequency based on how overdue the invoice is
        days_overdue = (timezone.now().date() - invoice.due_date).days
        
        if days_overdue <= 7:
            # Send reminder every 2 days in first week
            return days_since_last >= 2
        elif days_overdue <= 30:
            # Send reminder every 7 days until 30 days
            return days_since_last >= 7
        else:
            # Send reminder every 14 days after 30 days
            return days_since_last >= 14

    def send_overdue_reminder(self, invoice):
        """Send overdue invoice reminder."""
        context = {
            'invoice': invoice,
            'client': invoice.client,
            'company': invoice.company,
            'days_overdue': (timezone.now().date() - invoice.due_date).days,
            'balance_due': invoice.get_balance_due()
        }
        
        html_message = render_to_string(
            'financial_app/email/invoice_overdue_reminder.html',
            context
        )
        
        subject = f'Overdue Invoice Reminder - {invoice.invoice_number}'
        
        email = EmailMessage(
            subject=subject,
            body=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[invoice.client.email],
            cc=[invoice.company.owner.email]
        )
        
        # Attach invoice PDF
        pdf_file = InvoiceService.generate_pdf(invoice)
        email.attach(
            f'invoice_{invoice.invoice_number}.pdf',
            pdf_file,
            'application/pdf'
        )
        
        email.send()
        
        # Update reminder tracking
        invoice.last_reminder_sent = timezone.now()
        invoice.reminder_count += 1
        invoice.save()

    def send_upcoming_reminder(self, invoice):
        """Send upcoming payment reminder."""
        context = {
            'invoice': invoice,
            'client': invoice.client,
            'company': invoice.company,
            'days_until_due': (invoice.due_date - timezone.now().date()).days,
            'amount_due': invoice.get_balance_due()
        }
        
        html_message = render_to_string(
            'financial_app/email/upcoming_payment_reminder.html',
            context
        )
        
        subject = f'Payment Reminder - Invoice {invoice.invoice_number}'
        
        email = EmailMessage(
            subject=subject,
            body=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[invoice.client.email]
        )
        
        # Attach invoice PDF
        pdf_file = InvoiceService.generate_pdf(invoice)
        email.attach(
            f'invoice_{invoice.invoice_number}.pdf',
            pdf_file,
            'application/pdf'
        )
        
        email.send()

def format_currency(amount, currency='EUR'):
    """Helper function to format currency amounts."""
    symbols = {'EUR': '€', 'USD': '$', 'GBP': '£'}
    symbol = symbols.get(currency, '')
    return f"{symbol}{amount:,.2f}"