from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import datetime, timedelta
from ..models import ExpenseCategory

class DateRangeForm(forms.Form):
    """
    Base form for date range selection in reports
    """
    PERIOD_CHOICES = [
        ('custom', _('Custom Date Range')),
        ('today', _('Today')),
        ('yesterday', _('Yesterday')),
        ('this_week', _('This Week')),
        ('last_week', _('Last Week')),
        ('this_month', _('This Month')),
        ('last_month', _('Last Month')),
        ('this_quarter', _('This Quarter')),
        ('last_quarter', _('Last Quarter')),
        ('this_year', _('This Year')),
        ('last_year', _('Last Year')),
    ]

    period = forms.ChoiceField(
        choices=PERIOD_CHOICES,
        initial='this_month',
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        period = cleaned_data.get('period')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if period == 'custom':
            if not start_date or not end_date:
                raise forms.ValidationError(
                    _("Both start date and end date are required for custom date range")
                )
            if end_date < start_date:
                raise forms.ValidationError(
                    _("End date must be after start date")
                )
        else:
            # Calculate date range based on period selection
            today = timezone.now().date()
            
            if period == 'today':
                start_date = end_date = today
            elif period == 'yesterday':
                start_date = end_date = today - timedelta(days=1)
            elif period == 'this_week':
                start_date = today - timedelta(days=today.weekday())
                end_date = today
            elif period == 'last_week':
                start_date = today - timedelta(days=today.weekday() + 7)
                end_date = start_date + timedelta(days=6)
            elif period == 'this_month':
                start_date = today.replace(day=1)
                end_date = today
            elif period == 'last_month':
                last_month = today.replace(day=1) - timedelta(days=1)
                start_date = last_month.replace(day=1)
                end_date = last_month
            elif period == 'this_quarter':
                quarter = (today.month - 1) // 3
                start_date = today.replace(month=quarter * 3 + 1, day=1)
                end_date = today
            elif period == 'last_quarter':
                quarter = (today.month - 1) // 3
                if quarter == 0:
                    start_date = today.replace(year=today.year - 1, month=10, day=1)
                    end_date = today.replace(year=today.year - 1, month=12, day=31)
                else:
                    start_date = today.replace(month=(quarter - 1) * 3 + 1, day=1)
                    end_date = today.replace(month=quarter * 3, day=1) - timedelta(days=1)
            elif period == 'this_year':
                start_date = today.replace(month=1, day=1)
                end_date = today
            elif period == 'last_year':
                start_date = today.replace(year=today.year - 1, month=1, day=1)
                end_date = today.replace(year=today.year - 1, month=12, day=31)

            cleaned_data['start_date'] = start_date
            cleaned_data['end_date'] = end_date

        return cleaned_data

class ProfitLossReportForm(DateRangeForm):
    """
    Form for Profit & Loss report configuration
    """
    compare_previous = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text=_("Compare with previous period")
    )
    
    include_draft_invoices = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    expense_categories = forms.ModelMultipleChoiceField(
        queryset=ExpenseCategory.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-select',
            'size': '5'
        }),
        help_text=_("Select specific categories or leave empty for all")
    )

    group_by = forms.ChoiceField(
        choices=[
            ('month', _('Month')),
            ('quarter', _('Quarter')),
            ('year', _('Year')),
        ],
        initial='month',
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )

class CashFlowReportForm(DateRangeForm):
    """
    Form for Cash Flow report configuration
    """
    include_pending = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text=_("Include pending payments")
    )
    
    forecast_periods = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=12,
        initial=3,
        widget=forms.NumberInput(attrs={
            'class': 'form-control'
        }),
        help_text=_("Number of periods to forecast (0-12)")
    )

class TaxReportForm(DateRangeForm):
    """
    Form for Tax report configuration
    """
    tax_rate = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=100,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01'
        }),
        help_text=_("Override default tax rate for calculations")
    )
    
    include_tax_deductible_only = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )

class ReportExportForm(forms.Form):
    """
    Form for configuring report exports
    """
    FORMAT_CHOICES = [
        ('pdf', _('PDF')),
        ('xlsx', _('Excel')),
        ('csv', _('CSV')),
    ]
    
    format = forms.ChoiceField(
        choices=FORMAT_CHOICES,
        initial='pdf',
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    include_charts = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text=_("Include visual charts in the report")
    )
    
    paper_size = forms.ChoiceField(
        choices=[
            ('a4', 'A4'),
            ('letter', 'Letter'),
            ('legal', 'Legal')
        ],
        initial='a4',
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    orientation = forms.ChoiceField(
        choices=[
            ('portrait', _('Portrait')),
            ('landscape', _('Landscape'))
        ],
        initial='portrait',
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )