from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.core.mail import send_mail, EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from django.db.models import Q, Sum, F
import logging
from datetime import datetime, timedelta

from financial_app.models import (
    Company, Invoice, Expense, Client, 
    UserProfile, PaymentRecord
)

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Send automated notifications for various events'

    NOTIFICATION_TYPES = {
        'invoice_due': 'Invoice due date reminders',
        'payment_received': 'Payment received confirmations',
        'expense_approval': 'Expense approval requests',
        'low_balance': 'Low balance alerts',
        'report_ready': 'Report ready notifications',
        'account_summary': 'Account summary updates'
    }

    def add_arguments(self, parser):
        parser.add_argument(
            '--notification-types',
            nargs='+',
            choices=self.NOTIFICATION_TYPES.keys(),
            default=['invoice_due'],
            help='Types of notifications to send'
        )
        
        parser.add_argument(
            '--company-id',
            type=int,
            help='Send notifications for specific company'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview notifications without sending'
        )
        
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Show detailed debug information'
        )

    def handle(self, *args, **options):
        try:
            # Set up logging
            self.setup_logging(options['debug'])
            
            # Get companies to process
            companies = self.get_companies(options['company_id'])
            
            total_notifications = 0
            total_errors = 0
            
            for company in companies:
                try:
                    for notification_type in options['notification_types']:
                        sent, errors = self.process_notifications(
                            company,
                            notification_type,
                            options['dry_run']
                        )
                        total_notifications += sent
                        total_errors += errors
                except Exception as e:
                    logger.error(f"Error processing company {company.id}: {str(e)}")
                    total_errors += 1
                    continue
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Processed {total_notifications} notifications with {total_errors} errors"
                )
            )
            
        except Exception as e:
            logger.error(f"Notification process failed: {str(e)}")
            raise CommandError(f"Notification process failed: {str(e)}")

    def setup_logging(self, debug=False):
        """Configure logging for notification process."""
        log_dir = os.path.join(settings.BASE_DIR, 'logs', 'notifications')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        log_file = os.path.join(
            log_dir,
            f'notifications_{timezone.now().strftime("%Y%m%d")}.log'
        )
        
        logging.basicConfig(
            filename=log_file,
            level=logging.DEBUG if debug else logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )

    def get_companies(self, company_id=None):
        """Get companies to process."""
        if company_id:
            return Company.objects.filter(id=company_id)
        return Company.objects.filter(is_active=True)

    def process_notifications(self, company, notification_type, dry_run=False):
        """Process notifications for a company."""
        notification_methods = {
            'invoice_due': self.process_invoice_due_notifications,
            'payment_received': self.process_payment_notifications,
            'expense_approval': self.process_expense_approval_notifications,
            'low_balance': self.process_low_balance_notifications,
            'report_ready': self.process_report_notifications,
            'account_summary': self.process_account_summary_notifications
        }
        
        method = notification_methods.get(notification_type)
        if not method:
            raise CommandError(f"Unknown notification type: {notification_type}")
            
        return method(company, dry_run)

    def process_invoice_due_notifications(self, company, dry_run=False):
        """Process invoice due date notifications."""
        sent_count = 0
        error_count = 0
        
        # Get upcoming and overdue invoices
        upcoming_due = Invoice.objects.filter(
            company=company,
            status__in=['SENT', 'PARTIALLY_PAID'],
            due_date__range=[
                timezone.now().date(),
                timezone.now().date() + timedelta(days=7)
            ]
        )
        
        overdue = Invoice.objects.filter(
            company=company,
            status__in=['SENT', 'PARTIALLY_PAID'],
            due_date__lt=timezone.now().date()
        )
        
        # Process upcoming due invoices
        for invoice in upcoming_due:
            try:
                if self.should_send_invoice_reminder(invoice):
                    context = {
                        'invoice': invoice,
                        'days_until_due': (invoice.due_date - timezone.now().date()).days,
                        'company': company
                    }
                    
                    if not dry_run:
                        self.send_notification(
                            'invoice_upcoming_due',
                            context,
                            [invoice.client.email],
                            f"Payment Due Soon - Invoice {invoice.invoice_number}"
                        )
                    
                    sent_count += 1
                    logger.info(f"Sent upcoming due notification for invoice {invoice.id}")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing upcoming due invoice {invoice.id}: {str(e)}")
        
        # Process overdue invoices
        for invoice in overdue:
            try:
                if self.should_send_overdue_reminder(invoice):
                    context = {
                        'invoice': invoice,
                        'days_overdue': (timezone.now().date() - invoice.due_date).days,
                        'company': company
                    }
                    
                    if not dry_run:
                        self.send_notification(
                            'invoice_overdue',
                            context,
                            [invoice.client.email],
                            f"Overdue Invoice Reminder - {invoice.invoice_number}"
                        )
                    
                    sent_count += 1
                    logger.info(f"Sent overdue notification for invoice {invoice.id}")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing overdue invoice {invoice.id}: {str(e)}")
        
        return sent_count, error_count

    def process_payment_notifications(self, company, dry_run=False):
        """Process payment received notifications."""
        sent_count = 0
        error_count = 0
        
        recent_payments = PaymentRecord.objects.filter(
            invoice__company=company,
            status='COMPLETED',
            created_at__gte=timezone.now() - timedelta(hours=24),
            notification_sent=False
        )
        
        for payment in recent_payments:
            try:
                context = {
                    'payment': payment,
                    'invoice': payment.invoice,
                    'company': company
                }
                
                if not dry_run:
                    # Notify client
                    self.send_notification(
                        'payment_received_client',
                        context,
                        [payment.invoice.client.email],
                        f"Payment Received - Invoice {payment.invoice.invoice_number}"
                    )
                    
                    # Notify company
                    self.send_notification(
                        'payment_received_company',
                        context,
                        [company.owner.email],
                        f"Payment Received - {payment.amount}"
                    )
                    
                    payment.notification_sent = True
                    payment.save()
                
                sent_count += 2  # Two notifications per payment
                logger.info(f"Sent payment notifications for payment {payment.id}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing payment {payment.id}: {str(e)}")
        
        return sent_count, error_count

    def process_expense_approval_notifications(self, company, dry_run=False):
        """Process expense approval notifications."""
        sent_count = 0
        error_count = 0
        
        pending_expenses = Expense.objects.filter(
            company=company,
            approved_by__isnull=True,
            notification_sent=False
        )
        
        for expense in pending_expenses:
            try:
                context = {
                    'expense': expense,
                    'company': company,
                    'approval_url': self.get_approval_url(expense)
                }
                
                if not dry_run:
                    self.send_notification(
                        'expense_approval_needed',
                        context,
                        [company.owner.email],
                        f"Expense Approval Required - {expense.amount}"
                    )
                    
                    expense.notification_sent = True
                    expense.save()
                
                sent_count += 1
                logger.info(f"Sent approval notification for expense {expense.id}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing expense {expense.id}: {str(e)}")
        
        return sent_count, error_count

    def process_low_balance_notifications(self, company, dry_run=False):
        """Process low balance notifications."""
        sent_count = 0
        error_count = 0
        
        clients = Client.objects.filter(company=company, credit_limit__gt=0)
        
        for client in clients:
            try:
                balance = client.get_outstanding_balance()
                if balance > (client.credit_limit * Decimal('0.8')):
                    context = {
                        'client': client,
                        'balance': balance,
                        'credit_limit': client.credit_limit,
                        'company': company
                    }
                    
                    if not dry_run:
                        self.send_notification(
                            'low_balance_alert',
                            context,
                            [company.owner.email],
                            f"Credit Limit Alert - {client.name}"
                        )
                    
                    sent_count += 1
                    logger.info(f"Sent low balance alert for client {client.id}")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing client {client.id}: {str(e)}")
        
        return sent_count, error_count

    def process_report_notifications(self, company, dry_run=False):
        """Process report ready notifications."""
        # Implementation for report notifications
        pass

    def process_account_summary_notifications(self, company, dry_run=False):
        """Process account summary notifications."""
        # Implementation for account summary notifications
        pass

    def should_send_invoice_reminder(self, invoice):
        """Check if invoice reminder should be sent."""
        if not invoice.last_reminder_sent:
            return True
            
        days_since_last = (timezone.now() - invoice.last_reminder_sent).days
        
        if invoice.due_date > timezone.now().date():
            # Upcoming due dates
            days_until_due = (invoice.due_date - timezone.now().date()).days
            if days_until_due <= 1:
                return days_since_last >= 1
            elif days_until_due <= 3:
                return days_since_last >= 2
            else:
                return days_since_last >= 7
        else:
            # Overdue invoices
            days_overdue = (timezone.now().date() - invoice.due_date).days
            if days_overdue <= 7:
                return days_since_last >= 2
            elif days_overdue <= 30:
                return days_since_last >= 7
            else:
                return days_since_last >= 14

    def should_send_overdue_reminder(self, invoice):
        """Check if overdue reminder should be sent."""
        return self.should_send_invoice_reminder(invoice)

    def send_notification(self, template, context, recipients, subject):
        """Send email notification."""
        try:
            html_message = render_to_string(
                f'financial_app/email/{template}.html',
                context
            )
            
            email = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients
            )
            
            email.content_subtype = 'html'
            email.send()
            
            logger.info(f"Sent {template} notification to {', '.join(recipients)}")
            
        except Exception as e:
            logger.error(f"Failed to send notification: {str(e)}")
            raise

    def get_approval_url(self, expense):
        """Generate expense approval URL."""
        return f"{settings.BASE_URL}/expenses/{expense.id}/approve/"