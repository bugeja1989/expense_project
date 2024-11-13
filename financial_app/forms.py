from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import (
    Company, Client, Invoice, InvoiceItem, 
    Expense, ExpenseCategory, UserProfile, 
    PaymentRecord
)

class DateInput(forms.DateInput):
    input_type = 'date'

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
            UserProfile.objects.create(user=user)
        return user

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('role', 'language', 'phone', 'notification_preferences', 'avatar')
        widgets = {
            'notification_preferences': forms.CheckboxSelectMultiple(
                choices=[
                    ('email', _('Email Notifications')),
                    ('invoice', _('Invoice Updates')),
                    ('expense', _('Expense Alerts')),
                    ('payment', _('Payment Notifications')),
                ]
            )
        }

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        exclude = ('owner', 'created_at', 'updated_at')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'vat_number': forms.TextInput(attrs={'class': 'form-control'}),
            'registration_number': forms.TextInput(attrs={'class': 'form-control'}),
            'preferred_currency': forms.Select(attrs={'class': 'form-control'}),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'website': forms.URLInput(attrs={'class': 'form-control'}),
            'tax_number': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_account': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'swift_code': forms.TextInput(attrs={'class': 'form-control'}),
            'iban': forms.TextInput(attrs={'class': 'form-control'}),
            'default_payment_terms': forms.NumberInput(attrs={'class': 'form-control'}),
            'invoice_notes_template': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'invoice_footer': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_logo(self):
        logo = self.cleaned_data.get('logo')
        if logo:
            if logo.size > 5*1024*1024:  # 5MB
                raise ValidationError(_('Image file size cannot exceed 5MB.'))
        return logo

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        exclude = ('company', 'created_at', 'updated_at')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'vat_number': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'payment_terms': forms.NumberInput(attrs={'class': 'form-control'}),
            'credit_limit': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        exclude = ('company', 'invoice_number', 'subtotal', 'tax_amount', 
                  'total_amount', 'amount_paid', 'created_by', 'created_at', 
                  'updated_at', 'last_reminder_sent', 'reminder_count')
        widgets = {
            'client': forms.Select(attrs={'class': 'form-control'}),
            'issue_date': DateInput(attrs={'class': 'form-control'}),
            'due_date': DateInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'tax_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'terms': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'footer': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control'}),
            'is_recurring': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'recurring_frequency': forms.Select(attrs={'class': 'form-control'}),
            'next_recurring_date': DateInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        issue_date = cleaned_data.get('issue_date')
        due_date = cleaned_data.get('due_date')
        is_recurring = cleaned_data.get('is_recurring')
        recurring_frequency = cleaned_data.get('recurring_frequency')
        
        if due_date and issue_date and due_date < issue_date:
            raise ValidationError(_('Due date cannot be earlier than issue date'))
            
        if is_recurring and not recurring_frequency:
            raise ValidationError(_('Recurring frequency is required for recurring invoices'))
        
        return cleaned_data

class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        exclude = ('invoice', 'created_at', 'updated_at', 'total')
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'tax_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
        }

InvoiceItemFormSet = forms.inlineformset_factory(
    Invoice,
    InvoiceItem,
    form=InvoiceItemForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True
)

class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = '__all__'
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'parent': forms.Select(attrs={'class': 'form-control'}),
        }

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        exclude = ('company', 'created_at', 'updated_at', 'created_by', 
                  'approved_by', 'approval_date')
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'date': DateInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'receipt': forms.FileInput(attrs={'class': 'form-control'}),
            'vendor': forms.TextInput(attrs={'class': 'form-control'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control'}),
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
            'is_recurring': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'recurring_frequency': forms.Select(attrs={'class': 'form-control'}),
            'next_recurring_date': DateInput(attrs={'class': 'form-control'}),
            'tax_deductible': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tags': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_receipt(self):
        receipt = self.cleaned_data.get('receipt')
        if receipt:
            if receipt.size > 5*1024*1024:  # 5MB
                raise ValidationError(_('Receipt file size cannot exceed 5MB.'))
        return receipt

class PaymentRecordForm(forms.ModelForm):
    class Meta:
        model = PaymentRecord
        exclude = ('invoice', 'created_at', 'updated_at', 'processed_by')
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'payment_date': DateInput(attrs={'class': 'form-control'}),
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'transaction_id': forms.TextInput(attrs={'class': 'form-control'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'processing_fee': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
        }

class DateRangeForm(forms.Form):
    start_date = forms.DateField(
        widget=DateInput(attrs={'class': 'form-control'})
    )
    end_date = forms.DateField(
        widget=DateInput(attrs={'class': 'form-control'})
    )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and end_date < start_date:
            raise ValidationError(_('End date cannot be earlier than start date'))
        
        return cleaned_data

class InvoiceFilterForm(forms.Form):
    client = forms.ModelChoiceField(
        queryset=Client.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    status = forms.ChoiceField(
        choices=[('', '----')] + Invoice.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    date_from = forms.DateField(
        required=False,
        widget=DateInput(attrs={'class': 'form-control'})
    )
    date_to = forms.DateField(
        required=False,
        widget=DateInput(attrs={'class': 'form-control'})
    )
    min_amount = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    max_amount = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )

    def __init__(self, company, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client'].queryset = Client.objects.filter(company=company)

class ExpenseFilterForm(forms.Form):
    category = forms.ModelChoiceField(
        queryset=ExpenseCategory.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    date_from = forms.DateField(
        required=False,
        widget=DateInput(attrs={'class': 'form-control'})
    )
    date_to = forms.DateField(
        required=False,
        widget=DateInput(attrs={'class': 'form-control'})
    )
    min_amount = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    max_amount = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    tax_deductible = forms.ChoiceField(
        choices=[('', '----'), ('yes', 'Yes'), ('no', 'No')],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )