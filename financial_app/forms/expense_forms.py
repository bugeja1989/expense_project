from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from ..models import Expense, ExpenseCategory
import magic
import os
from decimal import Decimal

class ExpenseFilterForm(forms.Form):
    """
    Form for filtering expenses in reports and lists.
    """
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    category = forms.ModelChoiceField(
        queryset=ExpenseCategory.objects.all(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    min_amount = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01'
        })
    )
    max_amount = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01'
        })
    )
    vendor = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control'
        })
    )
    payment_method = forms.ChoiceField(
        choices=[('', '---')] + Expense.PAYMENT_METHOD_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    tax_deductible = forms.ChoiceField(
        choices=[
            ('', 'All'),
            ('yes', 'Tax Deductible Only'),
            ('no', 'Non-Tax Deductible Only')
        ],
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    tags = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'data-role': 'tagsinput'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        min_amount = cleaned_data.get('min_amount')
        max_amount = cleaned_data.get('max_amount')

        if date_from and date_to and date_from > date_to:
            raise ValidationError(_("End date must be after start date"))

        if min_amount and max_amount and min_amount > max_amount:
            raise ValidationError(_("Maximum amount must be greater than minimum amount"))

        return cleaned_data

class ExpenseCreateForm(forms.ModelForm):
    """
    Form for creating a new expense.
    """
    category_new = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Create new category')
        })
    )
    
    receipt_remove = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )

    class Meta:
        model = Expense
        fields = [
            'category', 'amount', 'date', 'description', 'receipt',
            'vendor', 'reference_number', 'payment_method', 'is_recurring',
            'recurring_frequency', 'next_recurring_date', 'tax_deductible',
            'tags', 'notes'
        ]
        widgets = {
            'category': forms.Select(attrs={
                'class': 'form-select'
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'receipt': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*, application/pdf'
            }),
            'vendor': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'reference_number': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'payment_method': forms.Select(attrs={
                'class': 'form-select'
            }),
            'is_recurring': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'recurring_frequency': forms.Select(attrs={
                'class': 'form-select'
            }),
            'next_recurring_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'tax_deductible': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'tags': forms.TextInput(attrs={
                'class': 'form-control',
                'data-role': 'tagsinput'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            })
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        
        if self.company:
            self.fields['category'].queryset = ExpenseCategory.objects.filter(
                is_active=True
            ).order_by('name')

    def clean_receipt(self):
        receipt = self.cleaned_data.get('receipt')
        if receipt:
            # Check file size
            if receipt.size > 5 * 1024 * 1024:  # 5MB limit
                raise ValidationError(_("Receipt file size cannot exceed 5MB"))

            # Check file type
            allowed_types = ['image/jpeg', 'image/png', 'application/pdf']
            file_type = magic.from_buffer(receipt.read(1024), mime=True)
            if file_type not in allowed_types:
                raise ValidationError(_("Invalid file type. Allowed types: JPG, PNG, PDF"))

            receipt.seek(0)
        return receipt

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        category_new = cleaned_data.get('category_new')
        is_recurring = cleaned_data.get('is_recurring')
        recurring_frequency = cleaned_data.get('recurring_frequency')
        next_recurring_date = cleaned_data.get('next_recurring_date')
        date = cleaned_data.get('date')

        # Handle new category creation
        if category_new and not category:
            category, created = ExpenseCategory.objects.get_or_create(
                name=category_new.strip(),
                defaults={'description': category_new.strip()}
            )
            cleaned_data['category'] = category

        # Validate recurring expense settings
        if is_recurring:
            if not recurring_frequency:
                raise ValidationError({
                    'recurring_frequency': _("Frequency is required for recurring expenses")
                })
            if not next_recurring_date:
                raise ValidationError({
                    'next_recurring_date': _("Next date is required for recurring expenses")
                })
            if next_recurring_date <= date:
                raise ValidationError({
                    'next_recurring_date': _("Next recurring date must be after expense date")
                })

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.company = self.company
        
        if commit:
            # Handle receipt removal
            if self.cleaned_data.get('receipt_remove') and instance.receipt:
                instance.receipt.delete()
                instance.receipt = None
            
            instance.save()
            
            # Create recurring schedule if needed
            if instance.is_recurring and instance.recurring_frequency:
                self.create_recurring_schedule(instance)
        
        return instance

class ExpenseBulkUploadForm(forms.Form):
    """
    Form for bulk uploading expenses via CSV/Excel file.
    """
    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv,.xlsx,.xls'
        }),
        help_text=_("Upload CSV or Excel file")
    )
    
    date_format = forms.ChoiceField(
        choices=[
            ('%Y-%m-%d', 'YYYY-MM-DD'),
            ('%d/%m/%Y', 'DD/MM/YYYY'),
            ('%m/%d/%Y', 'MM/DD/YYYY'),
        ],
        initial='%Y-%m-%d',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text=_("Select the date format used in your file")
    )

    category_mapping = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _("Enter category mappings (one per line): source_name=target_name")
        }),
        help_text=_("Map category names from your file to existing categories")
    )

    def clean_file(self):
        file = self.cleaned_data['file']
        ext = os.path.splitext(file.name)[1].lower()
        
        if ext not in ['.csv', '.xlsx', '.xls']:
            raise ValidationError(
                _("Unsupported file format. Please upload a CSV or Excel file.")
            )
        
        if file.size > 10 * 1024 * 1024:  # 10MB limit
            raise ValidationError(
                _("File size cannot exceed 10MB.")
            )
        
        return file

    def clean_category_mapping(self):
        mapping = self.cleaned_data['category_mapping']
        if not mapping:
            return {}
            
        result = {}
        for line in mapping.split('\n'):
            line = line.strip()
            if '=' in line:
                source, target = line.split('=', 1)
                result[source.strip()] = target.strip()
        
        return result

class ExpenseCategoryForm(forms.ModelForm):
    """
    Form for creating/editing expense categories.
    """
    class Meta:
        model = ExpenseCategory
        fields = ['name', 'description', 'is_active', 'parent']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'parent': forms.Select(attrs={
                'class': 'form-select'
            })
        }

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if ExpenseCategory.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_("A category with this name already exists"))
        return name

    def clean(self):
        cleaned_data = super().clean()
        parent = cleaned_data.get('parent')
        
        if parent and parent == self.instance:
            raise ValidationError({
                'parent': _("A category cannot be its own parent")
            })
            
        return cleaned_data