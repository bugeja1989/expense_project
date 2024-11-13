from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum
from django.core.files.storage import default_storage
import logging
from ..models import Expense, ExpenseCategory

logger = logging.getLogger(__name__)

class ExpenseService:
    @staticmethod
    def create_expense(company, category, amount, **kwargs):
        """
        Create a new expense record.
        """
        try:
            expense = Expense.objects.create(
                company=company,
                category=category,
                amount=amount,
                date=kwargs.get('date', timezone.now().date()),
                description=kwargs.get('description', ''),
                vendor=kwargs.get('vendor', ''),
                reference_number=kwargs.get('reference_number', ''),
                payment_method=kwargs.get('payment_method', 'CASH'),
                is_recurring=kwargs.get('is_recurring', False),
                recurring_frequency=kwargs.get('recurring_frequency', ''),
                tax_deductible=kwargs.get('tax_deductible', False),
                created_by=kwargs.get('created_by'),
                tags=kwargs.get('tags', ''),
                notes=kwargs.get('notes', '')
            )

            # Handle receipt upload
            receipt = kwargs.get('receipt')
            if receipt:
                expense.receipt = receipt
                expense.save()

            return expense
        except Exception as e:
            logger.error(f"Error creating expense: {str(e)}")
            raise

    @staticmethod
    def get_expense_summary(company, start_date=None, end_date=None):
        """
        Generate expense summary by category.
        """
        try:
            expenses = Expense.objects.filter(company=company)
            
            if start_date:
                expenses = expenses.filter(date__gte=start_date)
            if end_date:
                expenses = expenses.filter(date__lte=end_date)

            summary = expenses.values('category__name').annotate(
                total=Sum('amount')
            ).order_by('-total')

            return summary
        except Exception as e:
            logger.error(f"Error generating expense summary for company {company.id}: {str(e)}")
            raise

    @staticmethod
    def get_tax_deductible_expenses(company, tax_year):
        """
        Get all tax-deductible expenses for a specific tax year.
        """
        try:
            start_date = timezone.datetime(tax_year, 1, 1).date()
            end_date = timezone.datetime(tax_year, 12, 31).date()

            expenses = Expense.objects.filter(
                company=company,
                tax_deductible=True,
                date__range=[start_date, end_date]
            )

            total_deductible = expenses.aggregate(total=Sum('amount'))['total'] or 0
            
            return {
                'expenses': expenses,
                'total_deductible': total_deductible
            }
        except Exception as e:
            logger.error(f"Error getting tax deductible expenses for company {company.id}: {str(e)}")
            raise

    @staticmethod
    def approve_expense(expense, approver):
        """
        Approve an expense.
        """
        try:
            if expense.approved_by:
                raise ValueError("Expense is already approved")

            expense.approved_by = approver
            expense.approval_date = timezone.now()
            expense.save()
        except Exception as e:
            logger.error(f"Error approving expense {expense.id}: {str(e)}")
            raise

    @staticmethod
    def bulk_categorize_expenses(expenses, category):
        """
        Bulk categorize multiple expenses.
        """
        try:
            expenses.update(category=category)
        except Exception as e:
            logger.error("Error bulk categorizing expenses: {str(e)}")
            raise

    @staticmethod
    def get_recurring_expense_forecast(company, months=12):
        """
        Generate forecast for recurring expenses.
        """
        try:
            recurring_expenses = Expense.objects.filter(
                company=company,
                is_recurring=True
            )

            forecast = []
            current_date = timezone.now().date()

            for _ in range(months):
                month_total = Decimal('0')
                
                for expense in recurring_expenses:
                    if expense.recurring_frequency == 'MONTHLY':
                        month_total += expense.amount
                    elif expense.recurring_frequency == 'QUARTERLY' and current_date.month % 3 == 0:
                        month_total += expense.amount
                    elif expense.recurring_frequency == 'YEARLY' and current_date.month == expense.date.month:
                        month_total += expense.amount

                forecast.append({
                    'date': current_date,
                    'amount': month_total
                })
                
                # Move to next month
                if current_date.month == 12:
                    current_date = current_date.replace(year=current_date.year + 1, month=1)
                else:
                    current_date = current_date.replace(month=current_date.month + 1)

            return forecast
        except Exception as e:
            logger.error(f"Error generating expense forecast for company {company.id}: {str(e)}")
            raise