from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail, EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from django.db.models import Sum, Q
from datetime import timedelta
from decimal import Decimal
import csv
import io
import logging
from .models import (
    Invoice, Expense, Company, Client,
    PaymentRecord, UserProfile
)

logger = logging.getLogger(__name__)

@shared_task
def check_overdue_invoices():
    """
    Check for overdue invoices and send reminders.
    Runs daily.
    """
    today = timezone.now().date()
    
    # Find invoices that are overdue but not marked as overdue
    overdue_invoices = Invoice.objects.filter(
        Q(status='SENT') | Q(status='PARTIALLY_PAID'),
        due_date__lt=today
    )
    
    for invoice in overdue_invoices:
        try:
            # Update status
            invoice.status = 'OVERDUE'
            invoice.save()
            
            # Send reminder email
            context = {
                'invoice': invoice,
                'client': invoice.client,
                'company': invoice.company,
                'days_overdue': (today - invoice.due_date).days
            }
            
            html_message = render_to_string(
                'financial_app/email/invoice_overdue.html',
                context
            )
            
            send_mail(
                subject=f'Overdue Invoice Reminder - {invoice.invoice_number}',
                message='',
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[invoice.client.email],
                fail_silently=True
            )
            
            # Log the reminder
            invoice.last_reminder_sent = timezone.now()
            invoice.reminder_count += 1
            invoice.save()
            
        except Exception as e:
            logger.error(f"Error processing overdue invoice {invoice.id}: {str(e)}")

@shared_task
def generate_recurring_invoices():
    """
    Generate new invoices for recurring invoices.
    Runs daily.
    """
    today = timezone.now().date()
    
    recurring_invoices = Invoice.objects.filter(
        is_recurring=True,
        next_recurring_date__lte=today
    )
    
    for invoice in recurring_invoices:
        try:
            # Create new invoice
            new_invoice = Invoice.objects.create(
                company=invoice.company,
                client=invoice.client,
                status='DRAFT',
                issue_date=today,
                due_date=today + timedelta(days=invoice.company.default_payment_terms),
                tax_rate=invoice.tax_rate,
                notes=invoice.notes,
                terms=invoice.terms,
                footer=invoice.footer,
                is_recurring=True,
                recurring_frequency=invoice.recurring_frequency,
                next_recurring_date=calculate_next_recurring_date(today, invoice.recurring_frequency)
            )
            
            # Copy invoice items
            for item in invoice.items.all():
                item.pk = None
                item.invoice = new_invoice
                item.save()
            
            # Update original invoice's next recurring date
            invoice.next_recurring_date = calculate_next_recurring_date(
                today,
                invoice.recurring_frequency
            )
            invoice.save()
            
        except Exception as e:
            logger.error(f"Error generating recurring invoice {invoice.id}: {str(e)}")

@shared_task
def process_recurring_expenses():
    """
    Process recurring expenses.
    Runs daily.
    """
    today = timezone.now().date()
    
    recurring_expenses = Expense.objects.filter(
        is_recurring=True,
        next_recurring_date__lte=today
    )
    
    for expense in recurring_expenses:
        try:
            # Create new expense
            new_expense = Expense.objects.create(
                company=expense.company,
                category=expense.category,
                amount=expense.amount,
                date=today,
                description=expense.description,
                vendor=expense.vendor,
                payment_method=expense.payment_method,
                is_recurring=True,
                recurring_frequency=expense.recurring_frequency,
                next_recurring_date=calculate_next_recurring_date(today, expense.recurring_frequency),
                tax_deductible=expense.tax_deductible,
                created_by=expense.created_by,
                tags=expense.tags,
                notes=expense.notes
            )
            
            # Update original expense's next recurring date
            expense.next_recurring_date = calculate_next_recurring_date(
                today,
                expense.recurring_frequency
            )
            expense.save()
            
        except Exception as e:
            logger.error(f"Error processing recurring expense {expense.id}: {str(e)}")

@shared_task
def generate_monthly_reports():
    """
    Generate and send monthly financial reports.
    Runs on the 1st of each month.
    """
    today = timezone.now().date()
    first_of_month = today.replace(day=1)
    last_month = (first_of_month - timedelta(days=1))
    start_date = last_month.replace(day=1)
    
    for company in Company.objects.all():
        try:
            # Calculate monthly totals
            invoices = Invoice.objects.filter(
                company=company,
                issue_date__range=[start_date, last_month]
            )
            
            expenses = Expense.objects.filter(
                company=company,
                date__range=[start_date, last_month]
            )
            
            # Calculate totals
            revenue = invoices.filter(status='PAID').aggregate(
                total=Sum('total_amount')
            )['total'] or Decimal('0')
            
            expenses_total = expenses.aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')
            
            profit = revenue - expenses_total
            
            # Generate CSV report
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Monthly Financial Report', last_month.strftime('%B %Y')])
            writer.writerow([])
            writer.writerow(['Revenue', revenue])
            writer.writerow(['Expenses', expenses_total])
            writer.writerow(['Profit', profit])
            writer.writerow([])
            writer.writerow(['Expense Breakdown'])
            
            # Add expense categories
            for expense in expenses:
                writer.writerow([
                    expense.category.name,
                    expense.date.strftime('%Y-%m-%d'),
                    expense.amount
                ])
            
            # Create email
            subject = f'Monthly Financial Report - {last_month.strftime("%B %Y")}'
            context = {
                'company': company,
                'month': last_month.strftime('%B %Y'),
                'revenue': revenue,
                'expenses': expenses_total,
                'profit': profit
            }
            
            html_message = render_to_string(
                'financial_app/email/monthly_report.html',
                context
            )
            
            # Create email with attachment
            email = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[company.owner.email]
            )
            
            # Attach CSV report
            email.attach(
                f'financial_report_{last_month.strftime("%Y_%m")}.csv',
                output.getvalue(),
                'text/csv'
            )
            
            email.send(fail_silently=True)
            
        except Exception as e:
            logger.error(f"Error generating monthly report for company {company.id}: {str(e)}")

@shared_task
def backup_database():
    """
    Create a backup of the database.
    Runs daily.
    """
    try:
        # Implement your backup logic here
        pass
    except Exception as e:
        logger.error(f"Error creating database backup: {str(e)}")

@shared_task
def cleanup_old_files():
    """
    Clean up old temporary files and logs.
    Runs weekly.
    """
    try:
        # Implement your cleanup logic here
        pass
    except Exception as e:
        logger.error(f"Error cleaning up old files: {str(e)}")

def calculate_next_recurring_date(current_date, frequency):
    """Helper function to calculate next recurring date."""
    if frequency == 'DAILY':
        return current_date + timedelta(days=1)
    elif frequency == 'WEEKLY':
        return current_date + timedelta(weeks=1)
    elif frequency == 'MONTHLY':
        next_month = current_date + timedelta(days=32)
        return next_month.replace(day=1)
    elif frequency == 'QUARTERLY':
        next_quarter = current_date + timedelta(days=92)
        return next_quarter.replace(day=1)
    elif frequency == 'YEARLY':
        return current_date.replace(year=current_date.year + 1)
    return None

@shared_task
def send_low_balance_alerts():
    """
    Send alerts for clients approaching their credit limit.
    Runs daily.
    """
    for client in Client.objects.filter(credit_limit__gt=0):
        outstanding_balance = client.get_outstanding_balance()
        if outstanding_balance > (client.credit_limit * Decimal('0.8')):  # 80% of credit limit
            try:
                context = {
                    'client': client,
                    'outstanding_balance': outstanding_balance,
                    'credit_limit': client.credit_limit
                }
                
                html_message = render_to_string(
                    'financial_app/email/credit_limit_alert.html',
                    context
                )
                
                send_mail(
                    subject='Credit Limit Alert',
                    message='',
                    html_message=html_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[client.company.owner.email],
                    fail_silently=True
                )
            except Exception as e:
                logger.error(f"Error sending low balance alert for client {client.id}: {str(e)}")

@shared_task
def send_weekly_summary():
    """
    Send weekly summary of financial activities.
    Runs every Monday.
    """
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=7)
    
    for company in Company.objects.all():
        try:
            context = {
                'company': company,
                'period': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                'new_invoices': Invoice.objects.filter(
                    company=company,
                    created_at__range=[start_date, end_date]
                ).count(),
                'paid_invoices': Invoice.objects.filter(
                    company=company,
                    status='PAID',
                    updated_at__range=[start_date, end_date]
                ).count(),
                'new_expenses': Expense.objects.filter(
                    company=company,
                    created_at__range=[start_date, end_date]
                ).count()
            }
            
            html_message = render_to_string(
                'financial_app/email/weekly_summary.html',
                context
            )
            
            send_mail(
                subject='Weekly Financial Summary',
                message='',
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[company.owner.email],
                fail_silently=True
            )
            
        except Exception as e:
            logger.error(f"Error sending weekly summary for company {company.id}: {str(e)}")