from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, PasswordChangeForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from ..models import UserProfile

class CustomUserCreationForm(UserCreationForm):
    """
    Extended user registration form with additional fields
    """
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': _('Email address')
        })
    )
    
    first_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('First name')
        })
    )
    
    last_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Last name')
        })
    )
    
    role = forms.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        initial='VIEWER',
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    language = forms.ChoiceField(
        choices=UserProfile.LANGUAGE_CHOICES,
        initial='EN',
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    phone = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Phone number')
        })
    )
    
    terms_accepted = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 
                 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Username')
            })
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError(_("This email is already registered"))
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        
        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                role=self.cleaned_data['role'],
                language=self.cleaned_data['language'],
                phone=self.cleaned_data['phone']
            )
        return user

class UserProfileForm(forms.ModelForm):
    """
    Form for updating user profile settings
    """
    class Meta:
        model = UserProfile
        fields = ('language', 'phone', 'notification_preferences', 'avatar')
        widgets = {
            'language': forms.Select(attrs={
                'class': 'form-select'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'avatar': forms.FileInput(attrs={
                'class': 'form-control'
            })
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar:
            if avatar.size > 2 * 1024 * 1024:  # 2MB limit
                raise ValidationError(_("Image file too large ( > 2MB )"))
            return avatar
        return None

class NotificationPreferencesForm(forms.Form):
    """
    Form for updating notification preferences
    """
    invoice_created = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    payment_received = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    expense_approved = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    client_created = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    overdue_invoices = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    low_credit_limit = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    
    notification_method = forms.MultipleChoiceField(
        choices=[
            ('email', _('Email')),
            ('sms', _('SMS')),
            ('web', _('Web Notifications'))
        ],
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input'
        })
    )

class UserSettingsForm(forms.ModelForm):
    """
    Form for user account settings
    """
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control'
        }),
        required=False
    )
    
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name')
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'form-control'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control'
            })
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.exclude(pk=self.instance.pk).filter(email=email).exists():
            raise ValidationError(_("This email is already registered"))
        return email

    def clean(self):
        cleaned_data = super().clean()
        if self.changed_data and 'current_password' not in cleaned_data:
            raise ValidationError(
                _("Please enter your current password to save changes")
            )
        return cleaned_data

class TwoFactorSetupForm(forms.Form):
    """
    Form for setting up two-factor authentication
    """
    setup_method = forms.ChoiceField(
        choices=[
            ('authenticator', _('Authenticator App')),
            ('sms', _('SMS')),
            ('email', _('Email'))
        ],
        widget=forms.RadioSelect(attrs={
            'class': 'form-check-input'
        })
    )
    
    phone_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control'
        })
    )
    
    verification_code = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Enter verification code')
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get('setup_method')
        phone = cleaned_data.get('phone_number')
        
        if method == 'sms' and not phone:
            raise ValidationError({
                'phone_number': _("Phone number is required for SMS verification")
            })
            
        return cleaned_data

class AccountDeletionForm(forms.Form):
    """
    Form for account deletion
    """
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control'
        })
    )
    
    confirmation = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        label=_("I understand this action cannot be undone")
    )
    
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('Please tell us why you\'re leaving (optional)')
        })
    )
    
    transfer_data = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        label=_("Export my data before deletion")
    )