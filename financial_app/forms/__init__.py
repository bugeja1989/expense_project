from .invoice_forms import (
    InvoiceCreateForm,
    InvoiceUpdateForm,
    RecurringInvoiceForm,
    InvoiceBulkActionForm
)

from .expense_forms import (
    ExpenseCreateForm,
    ExpenseBulkUploadForm,
    ExpenseFilterForm,
    ExpenseCategoryForm
)

from .payment_forms import (
    PaymentRecordForm,
    BulkPaymentForm,
    PaymentRefundForm
)

from .client_forms import (
    ClientForm,
    ClientBulkUploadForm,
    ClientNoteForm,
    ClientFilterForm
)

from .report_forms import (
    DateRangeForm,
    ProfitLossReportForm,
    CashFlowReportForm,
    TaxReportForm,
    ReportExportForm
)

from .user_forms import (
    CustomUserCreationForm,
    UserProfileForm,
    NotificationPreferencesForm,
    UserSettingsForm,
    TwoFactorSetupForm,
    AccountDeletionForm
)

__all__ = [
    # Invoice Forms
    'InvoiceCreateForm',
    'InvoiceUpdateForm',
    'RecurringInvoiceForm',
    'InvoiceBulkActionForm',
    
    # Expense Forms
    'ExpenseCreateForm',
    'ExpenseBulkUploadForm',
    'ExpenseFilterForm',
    'ExpenseCategoryForm',
    
    # Payment Forms
    'PaymentRecordForm',
    'BulkPaymentForm',
    'PaymentRefundForm',
    
    # Client Forms
    'ClientForm',
    'ClientBulkUploadForm',
    'ClientNoteForm',
    'ClientFilterForm',
    
    # Report Forms
    'DateRangeForm',
    'ProfitLossReportForm',
    'CashFlowReportForm',
    'TaxReportForm',
    'ReportExportForm',
    
    # User Forms
    'CustomUserCreationForm',
    'UserProfileForm',
    'NotificationPreferencesForm',
    'UserSettingsForm',
    'TwoFactorSetupForm',
    'AccountDeletionForm'
]

# Form Sets for related models
from django.forms import inlineformset_factory
from ..models import Invoice, InvoiceItem

InvoiceItemFormSet = inlineformset_factory(
    Invoice,
    InvoiceItem,
    fields=('description', 'quantity', 'unit_price', 'tax_rate'),
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True
)

# Custom Form Widgets
from django import forms

class DatePickerInput(forms.DateInput):
    """Custom widget for date picker with Bootstrap styling"""
    def __init__(self, attrs=None):
        default_attrs = {'type': 'date', 'class': 'form-control'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

class TimePickerInput(forms.TimeInput):
    """Custom widget for time picker with Bootstrap styling"""
    def __init__(self, attrs=None):
        default_attrs = {'type': 'time', 'class': 'form-control'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

class DateTimePickerInput(forms.DateTimeInput):
    """Custom widget for datetime picker with Bootstrap styling"""
    def __init__(self, attrs=None):
        default_attrs = {'type': 'datetime-local', 'class': 'form-control'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

class MoneyInput(forms.NumberInput):
    """Custom widget for monetary inputs"""
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control',
            'step': '0.01',
            'min': '0'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

class PercentageInput(forms.NumberInput):
    """Custom widget for percentage inputs"""
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control',
            'step': '0.01',
            'min': '0',
            'max': '100'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

# Form Utilities
def clean_currency_field(value):
    """Utility function to clean currency inputs"""
    if isinstance(value, str):
        value = value.replace(',', '').strip()
        try:
            return float(value)
        except ValueError:
            raise forms.ValidationError(_("Please enter a valid amount"))
    return value

def clean_percentage_field(value):
    """Utility function to clean percentage inputs"""
    value = clean_currency_field(value)
    if value and (value < 0 or value > 100):
        raise forms.ValidationError(_("Percentage must be between 0 and 100"))
    return value

# Error messages
FORM_ERRORS = {
    'required': _("This field is required."),
    'invalid': _("Please enter a valid value."),
    'max_length': _("This value is too long."),
    'min_length': _("This value is too short."),
    'max_value': _("This value is too large."),
    'min_value': _("This value is too small."),
    'invalid_choice': _("Please select a valid choice."),
    'invalid_date': _("Please enter a valid date."),
    'invalid_time': _("Please enter a valid time."),
    'invalid_datetime': _("Please enter a valid date and time."),
    'invalid_email': _("Please enter a valid email address."),
    'invalid_url': _("Please enter a valid URL."),
    'invalid_integer': _("Please enter a valid integer."),
    'invalid_decimal': _("Please enter a valid decimal number."),
    'invalid_file': _("Please upload a valid file."),
    'invalid_image': _("Please upload a valid image file."),
    'password_mismatch': _("The two password fields didn't match."),
    'duplicate_email': _("This email address is already in use."),
    'duplicate_username': _("This username is already taken."),
    'password_too_short': _("Password must be at least 8 characters long."),
    'password_too_common': _("Password is too common."),
    'password_entirely_numeric': _("Password cannot be entirely numeric."),
}
