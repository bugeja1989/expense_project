from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from ..forms import (
    CustomUserCreationForm, UserProfileForm, 
    NotificationPreferencesForm, UserSettingsForm,
    TwoFactorSetupForm, AccountDeletionForm
)
from ..models import UserProfile, Company
from ..services.analytics_service import AnalyticsService

@login_required
def profile_view(request):
    """
    Display and update user profile information.
    """
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)

    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        settings_form = UserSettingsForm(request.POST, instance=request.user)
        
        if form.is_valid() and settings_form.is_valid():
            try:
                with transaction.atomic():
                    # Verify current password
                    current_password = settings_form.cleaned_data.get('current_password')
                    if current_password and not request.user.check_password(current_password):
                        messages.error(request, _("Current password is incorrect"))
                        raise ValueError("Invalid password")
                    
                    # Save user settings
                    settings_form.save()
                    
                    # Save profile
                    profile = form.save()
                    
                    messages.success(request, _("Profile updated successfully"))
                    return redirect('profile_view')
                    
            except ValueError:
                pass  # Error message already set
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = UserProfileForm(instance=profile)
        settings_form = UserSettingsForm(instance=request.user)

    context = {
        'form': form,
        'settings_form': settings_form,
        'profile': profile
    }

    return render(request, 'financial_app/user/profile.html', context)

@login_required
def notification_preferences(request):
    """
    Manage notification preferences.
    """
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)

    if request.method == 'POST':
        form = NotificationPreferencesForm(request.POST)
        if form.is_valid():
            try:
                preferences = {
                    'invoice_created': form.cleaned_data['invoice_created'],
                    'payment_received': form.cleaned_data['payment_received'],
                    'expense_approved': form.cleaned_data['expense_approved'],
                    'client_created': form.cleaned_data['client_created'],
                    'overdue_invoices': form.cleaned_data['overdue_invoices'],
                    'low_credit_limit': form.cleaned_data['low_credit_limit'],
                    'notification_method': form.cleaned_data['notification_method']
                }
                
                profile.notification_preferences = preferences
                profile.save()
                
                messages.success(request, _("Notification preferences updated successfully"))
                return redirect('notification_preferences')
                
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = NotificationPreferencesForm(initial=profile.notification_preferences)

    context = {
        'form': form,
        'profile': profile
    }

    return render(request, 'financial_app/user/notifications.html', context)

@login_required
def two_factor_setup(request):
    """
    Set up two-factor authentication.
    """
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)

    if request.method == 'POST':
        form = TwoFactorSetupForm(request.POST)
        if form.is_valid():
            try:
                setup_method = form.cleaned_data['setup_method']
                verification_code = form.cleaned_data['verification_code']
                
                if setup_method == 'sms':
                    phone = form.cleaned_data['phone_number']
                    if not phone:
                        raise ValueError(_("Phone number is required for SMS verification"))
                    profile.phone = phone
                
                # Verify the setup code
                if not verify_2fa_setup(request.user, setup_method, verification_code):
                    messages.error(request, _("Invalid verification code"))
                    raise ValueError("Invalid code")
                
                profile.two_factor_method = setup_method
                profile.save()
                
                messages.success(request, _("Two-factor authentication enabled successfully"))
                return redirect('profile_view')
                
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, _("An error occurred during setup"))
    else:
        form = TwoFactorSetupForm()

    context = {
        'form': form,
        'profile': profile
    }

    return render(request, 'financial_app/user/two_factor_setup.html', context)

@login_required
def account_deletion(request):
    """
    Handle account deletion request.
    """
    if request.method == 'POST':
        form = AccountDeletionForm(request.POST)
        if form.is_valid():
            try:
                # Verify password
                if not request.user.check_password(form.cleaned_data['password']):
                    messages.error(request, _("Invalid password"))
                    raise ValueError("Invalid password")
                
                with transaction.atomic():
                    # Export data if requested
                    if form.cleaned_data['transfer_data']:
                        export_user_data(request.user)
                    
                    # Record deletion reason
                    reason = form.cleaned_data.get('reason')
                    if reason:
                        log_account_deletion(request.user, reason)
                    
                    # Delete user account
                    request.user.delete()
                    
                    messages.success(request, _("Your account has been deleted"))
                    return redirect('home')
                    
            except ValueError:
                pass  # Error message already set
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = AccountDeletionForm()

    context = {
        'form': form
    }

    return render(request, 'financial_app/user/delete_account.html', context)

@login_required
def user_activity(request):
    """
    Display user activity history.
    """
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)

    # Get activity logs
    activity = get_user_activity(request.user)
    
    # Get user statistics
    stats = {
        'total_logins': activity.filter(action='login').count(),
        'last_login': profile.last_active,
        'total_transactions': activity.filter(
            action__in=['create_invoice', 'record_payment', 'create_expense']
        ).count()
    }

    context = {
        'activity': activity,
        'stats': stats,
        'profile': profile
    }

    return render(request, 'financial_app/user/activity.html', context)

@login_required
def user_dashboard(request):
    """
    Personal user dashboard with key metrics and recent activity.
    """
    try:
        company = request.user.company
    except Company.DoesNotExist:
        return redirect('company_setup')

    # Get personal metrics
    metrics = AnalyticsService.get_user_metrics(request.user)
    
    # Get recent activity
    activity = get_user_activity(request.user, limit=10)
    
    # Get upcoming tasks/reminders
    tasks = get_user_tasks(request.user)

    context = {
        'metrics': metrics,
        'activity': activity,
        'tasks': tasks
    }

    return render(request, 'financial_app/user/dashboard.html', context)

def verify_2fa_setup(user, method, code):
    """Helper function to verify 2FA setup."""
    # Implementation would depend on your 2FA provider
    return True  # Placeholder

def export_user_data(user):
    """Helper function to export user data."""
    # Implementation for data export
    pass

def log_account_deletion(user, reason):
    """Helper function to log account deletion."""
    # Implementation for deletion logging
    pass

def get_user_activity(user, limit=None):
    """Helper function to get user activity logs."""
    from django.contrib.admin.models import LogEntry
    activity = LogEntry.objects.filter(user=user).select_related('content_type')
    if limit:
        activity = activity[:limit]
    return activity

def get_user_tasks(user):
    """Helper function to get user tasks/reminders."""
    # Implementation for tasks/reminders
    return []