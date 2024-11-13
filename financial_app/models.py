from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, EmailValidator, RegexValidator
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.db.models import Sum
from datetime import datetime, timedelta
import uuid

class TimeStampedModel(models.Model):
    """Abstract base class with created and updated timestamps."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class UserProfile(TimeStampedModel):
    ROLE_CHOICES = [
        ('ADMIN', 'Admin'),
        ('ACCOUNTANT', 'Accountant'),
        ('VIEWER', 'Viewer')
    ]
    
    LANGUAGE_CHOICES = [
        ('EN', 'English'),
        ('MT', 'Maltese'),
        ('IT', 'Italian')
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='VIEWER')
    language = models.CharField(max_length=2, choices=LANGUAGE_CHOICES, default='EN')
    phone = models.CharField(
        max_length=20, 
        blank=True,
        validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$')]
    )
    notification_preferences = models.JSONField(
        default=dict,
        help_text=_('User notification preferences in JSON format')
    )
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = _('User Profile')
        verbose_name_plural = _('User Profiles')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.role}"
    
    def get_absolute_url(self):
        return reverse('user_profile_detail', args=[str(self.id)])

class Company(TimeStampedModel):
    CURRENCY_CHOICES = [
        ('EUR', 'Euro'),
        ('USD', 'US Dollar'),
        ('GBP', 'British Pound')
    ]
    
    name = models.CharField(
        max_length=200,
        validators=[RegexValidator(regex=r'^[\w\s-]+$')]
    )
    owner = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name='owned_companies'
    )
    vat_number = models.CharField(max_length=50, blank=True)
    registration_number = models.CharField(max_length=50, blank=True)
    preferred_currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='EUR'
    )
    logo = models.ImageField(
        upload_to='company_logos/',
        null=True,
        blank=True,
        help_text=_('Company logo (max 5MB)')
    )
    address = models.TextField(blank=True)
    phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$')]
    )
    email = models.EmailField(
        blank=True,
        validators=[EmailValidator()]
    )
    website = models.URLField(blank=True)
    tax_number = models.CharField(max_length=50, blank=True)
    bank_account = models.CharField(max_length=50, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    swift_code = models.CharField(max_length=20, blank=True)
    iban = models.CharField(max_length=50, blank=True)
    default_payment_terms = models.PositiveIntegerField(
        default=30,
        help_text=_('Default payment terms in days')
    )
    invoice_notes_template = models.TextField(
        blank=True,
        help_text=_('Default template for invoice notes')
    )
    invoice_footer = models.TextField(
        blank=True,
        help_text=_('Default footer text for invoices')
    )

    class Meta:
        verbose_name = _('Company')
        verbose_name_plural = _('Companies')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['owner']),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.logo and self.logo.size > 5*1024*1024:  # 5MB limit
            raise ValidationError(_('Logo file size cannot exceed 5MB'))
    
    def get_absolute_url(self):
        return reverse('company_detail', args=[str(self.id)])

    def get_total_revenue(self, start_date=None, end_date=None):
        """Calculate total revenue for given period."""
        invoices = self.invoice_set.filter(status='PAID')
        if start_date:
            invoices = invoices.filter(issue_date__gte=start_date)
        if end_date:
            invoices = invoices.filter(issue_date__lte=end_date)
        return invoices.aggregate(total=Sum('total_amount'))['total'] or 0

    def get_total_expenses(self, start_date=None, end_date=None):
        """Calculate total expenses for given period."""
        expenses = self.expense_set.all()
        if start_date:
            expenses = expenses.filter(date__gte=start_date)
        if end_date:
            expenses = expenses.filter(date__lte=end_date)
        return expenses.aggregate(total=Sum('amount'))['total'] or 0

class Client(TimeStampedModel):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='clients'
    )
    name = models.CharField(max_length=200)
    email = models.EmailField(validators=[EmailValidator()])
    phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$')]
    )
    address = models.TextField()
    vat_number = models.CharField(max_length=50, blank=True)
    contact_person = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    payment_terms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_('Client-specific payment terms in days')
    )
    credit_limit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)]
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _('Client')
        verbose_name_plural = _('Clients')
        ordering = ['name']
        unique_together = ['company', 'email']
        indexes = [
            models.Index(fields=['company', 'name']),
            models.Index(fields=['email']),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('client_detail', args=[str(self.id)])

    def get_outstanding_balance(self):
        """Calculate total outstanding balance for the client."""
        return self.invoice_set.filter(
            status__in=['SENT', 'OVERDUE']
        ).aggregate(
            total=Sum('total_amount')
        )['total'] or 0

    def is_credit_limit_exceeded(self):
        """Check if client has exceeded their credit limit."""
        if not self.credit_limit:
            return False
        return self.get_outstanding_balance() > self.credit_limit

class Invoice(TimeStampedModel):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SENT', 'Sent'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
        ('CANCELLED', 'Cancelled'),
        ('PARTIALLY_PAID', 'Partially Paid'),
    ]
    
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='invoices'
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='invoices'
    )
    invoice_number = models.CharField(max_length=50, unique=True, blank=True)
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='DRAFT'
    )
    issue_date = models.DateField()
    due_date = models.DateField()
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    amount_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    notes = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    footer = models.TextField(blank=True)
    reference_number = models.CharField(max_length=50, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_invoices'
    )
    last_reminder_sent = models.DateTimeField(null=True, blank=True)
    reminder_count = models.PositiveIntegerField(default=0)
    is_recurring = models.BooleanField(default=False)
    recurring_frequency = models.CharField(max_length=20, blank=True)
    next_recurring_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = _('Invoice')
        verbose_name_plural = _('Invoices')
        ordering = ['-issue_date']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['client', 'status']),
            models.Index(fields=['issue_date']),
            models.Index(fields=['due_date']),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.client.name}"

    def save(self, *args, **kwargs):
        # Generate invoice number if not set
        if not self.invoice_number:
            year = timezone.now().year
            month = timezone.now().month
            random_string = get_random_string(length=4, allowed_chars='1234567890')
            self.invoice_number = f"INV-{year}{month:02d}-{random_string}"
        
        # Calculate totals
        self.subtotal = sum(item.total for item in self.items.all())
        self.tax_amount = self.subtotal * (self.tax_rate / 100)
        self.total_amount = self.subtotal + self.tax_amount
        
        # Update status based on payments
        if self.amount_paid >= self.total_amount:
            self.status = 'PAID'
        elif self.amount_paid > 0:
            self.status = 'PARTIALLY_PAID'
        elif self.status == 'SENT' and self.due_date < timezone.now().date():
            self.status = 'OVERDUE'
        
        super().save(*args, **kwargs)

    def clean(self):
        if self.due_date and self.issue_date and self.due_date < self.issue_date:
            raise ValidationError(_('Due date cannot be earlier than issue date'))
        
        if self.client and self.client.company != self.company:
            raise ValidationError(_('Client must belong to the same company'))

    def get_absolute_url(self):
        return reverse('invoice_detail', args=[str(self.id)])

    def get_balance_due(self):
        """Calculate remaining balance due on invoice."""
        return self.total_amount - self.amount_paid

    def is_overdue(self):
        """Check if invoice is overdue."""
        return (
            self.status not in ['PAID', 'CANCELLED'] and
            self.due_date < timezone.now().date()
        )

    def send_reminder(self):
        """Send payment reminder to client."""
        from .tasks import send_invoice_reminder
        send_invoice_reminder.delay(self.id)
        self.last_reminder_sent = timezone.now()
        self.reminder_count += 1
        self.save()

class InvoiceItem(TimeStampedModel):
    invoice = models.ForeignKey(
        Invoice,
        related_name='items',
        on_delete=models.CASCADE
    )
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )

    class Meta:
        verbose_name = _('Invoice Item')
        verbose_name_plural = _('Invoice Items')

    def save(self, *args, **kwargs):
        self.total = self.quantity * self.unit_price
        if self.tax_rate:
            self.total += self.total * (self.tax_rate / 100)
        super().save(*args, **kwargs)
        self.invoice.save()  # Update invoice totals

class ExpenseCategory(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='subcategories'
    )

    class Meta:
        verbose_name = _('Expense Category')
        verbose_name_plural = _('Expense Categories')
        ordering = ['name']

    def __str__(self):
        return self.name

class Expense(TimeStampedModel):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='expenses'
    )
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name='expenses'
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    date = models.DateField()
    description = models.TextField()
    receipt = models.FileField(
        upload_to='receipts/',
        null=True,
        blank=True,
        help_text=_('Receipt image or PDF (max 5MB)')
    )
    vendor = models.CharField(max_length=200, blank=True)
    reference_number = models.CharField(max_length=50, blank=True)
    payment_method = models.CharField(
        max_length=50,
        choices=[
            ('CASH', 'Cash'),
            ('BANK_TRANSFER', 'Bank Transfer'),
            ('CREDIT_CARD', 'Credit Card'),
            ('DEBIT_CARD', 'Debit Card'),
            ('CHECK', 'Check'),
            ('OTHER', 'Other')
        ],
        default='CASH'
    )
    is_recurring = models.BooleanField(default=False)
    recurring_frequency = models.CharField(
        max_length=20,
        choices=[
            ('DAILY', 'Daily'),
            ('WEEKLY', 'Weekly'),
            ('MONTHLY', 'Monthly'),
            ('QUARTERLY', 'Quarterly'),
            ('YEARLY', 'Yearly')
        ],
        blank=True
    )
    next_recurring_date = models.DateField(null=True, blank=True)
    tax_deductible = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_expenses'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_expenses'
    )
    approval_date = models.DateTimeField(null=True, blank=True)
    tags = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _('Expense')
        verbose_name_plural = _('Expenses')
        ordering = ['-date']
        indexes = [
            models.Index(fields=['company', 'date']),
            models.Index(fields=['category']),
            models.Index(fields=['created_by']),
        ]

    def __str__(self):
        return f"{self.category.name} - {self.amount} ({self.date})"

    def clean(self):
        if self.receipt and self.receipt.size > 5*1024*1024:  # 5MB limit
            raise ValidationError(_('Receipt file size cannot exceed 5MB'))
        
        if self.is_recurring and not self.recurring_frequency:
            raise ValidationError(_('Recurring frequency is required for recurring expenses'))
        
        if self.approved_by and not self.approval_date:
            raise ValidationError(_('Approval date is required when expense is approved'))

    def get_absolute_url(self):
        return reverse('expense_detail', args=[str(self.id)])

    def approve(self, user):
        """Approve the expense."""
        if self.approved_by:
            raise ValidationError(_('Expense is already approved'))
        
        self.approved_by = user
        self.approval_date = timezone.now()
        self.save()

    def generate_next_recurring_expense(self):
        """Generate the next recurring expense based on frequency."""
        if not self.is_recurring or not self.recurring_frequency:
            return None

        next_date = self.next_recurring_date or self.date
        
        # Calculate next date based on frequency
        if self.recurring_frequency == 'DAILY':
            next_date += timedelta(days=1)
        elif self.recurring_frequency == 'WEEKLY':
            next_date += timedelta(weeks=1)
        elif self.recurring_frequency == 'MONTHLY':
            next_date = next_date + timedelta(days=32)
            next_date = next_date.replace(day=1) - timedelta(days=1)
        elif self.recurring_frequency == 'QUARTERLY':
            next_date = next_date + timedelta(days=92)
            next_date = next_date.replace(day=1) - timedelta(days=1)
        elif self.recurring_frequency == 'YEARLY':
            next_date = next_date.replace(year=next_date.year + 1)

        # Create new expense
        new_expense = Expense.objects.create(
            company=self.company,
            category=self.category,
            amount=self.amount,
            date=next_date,
            description=self.description,
            vendor=self.vendor,
            payment_method=self.payment_method,
            is_recurring=True,
            recurring_frequency=self.recurring_frequency,
            next_recurring_date=next_date,
            tax_deductible=self.tax_deductible,
            created_by=self.created_by,
            tags=self.tags,
            notes=self.notes
        )
        
        return new_expense

    def get_tax_amount(self):
        """Calculate tax amount if expense is tax deductible."""
        if not self.tax_deductible:
            return 0
        # Implement tax calculation logic based on your requirements
        return self.amount * 0.20  # Example: 20% tax deduction

class PaymentRecord(TimeStampedModel):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
        ('CANCELLED', 'Cancelled')
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('CREDIT_CARD', 'Credit Card'),
        ('CASH', 'Cash'),
        ('CHECK', 'Check'),
        ('STRIPE', 'Stripe'),
        ('PAYPAL', 'PayPal'),
        ('OTHER', 'Other')
    ]
    
    invoice = models.ForeignKey(
        Invoice,
        related_name='payments',
        on_delete=models.CASCADE
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    payment_date = models.DateField()
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='PENDING'
    )
    transaction_id = models.CharField(max_length=100, blank=True)
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='processed_payments'
    )
    processing_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )

    class Meta:
        verbose_name = _('Payment Record')
        verbose_name_plural = _('Payment Records')
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['invoice', 'status']),
            models.Index(fields=['payment_date']),
        ]

    def __str__(self):
        return f"Payment {self.id} for Invoice {self.invoice.invoice_number}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        # Update invoice amount paid and status
        if self.status == 'COMPLETED':
            self.invoice.amount_paid = self.invoice.payments.filter(
                status='COMPLETED'
            ).aggregate(
                total=Sum('amount')
            )['total'] or 0
            self.invoice.save()