from rest_framework import permissions
from ..models import UserProfile

class IsCompanyOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of a company to access it.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return obj.owner == request.user
        
        # Write permissions are only allowed to the owner
        return obj.owner == request.user

class HasCompanyAccess(permissions.BasePermission):
    """
    Permission to check if user has access to company-related objects
    based on their role.
    """
    def has_permission(self, request, view):
        try:
            profile = request.user.profile
            # Admins and accountants have full access
            if profile.role in ['ADMIN', 'ACCOUNTANT']:
                return True
            # Viewers only have read access
            elif profile.role == 'VIEWER':
                return request.method in permissions.SAFE_METHODS
            return False
        except UserProfile.DoesNotExist:
            return False

    def has_object_permission(self, request, view, obj):
        try:
            profile = request.user.profile
            company = getattr(obj, 'company', None)
            if not company:
                return False

            # Check if user has access to this company
            if company.owner == request.user:
                return True

            # Role-based permissions
            if profile.role == 'ADMIN':
                return True
            elif profile.role == 'ACCOUNTANT':
                # Accountants can do everything except delete
                return request.method != 'DELETE'
            elif profile.role == 'VIEWER':
                # Viewers can only view
                return request.method in permissions.SAFE_METHODS
            return False
        except UserProfile.DoesNotExist:
            return False

class CanApproveExpenses(permissions.BasePermission):
    """
    Permission to check if user can approve expenses.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        try:
            profile = request.user.profile
            return profile.role in ['ADMIN', 'ACCOUNTANT']
        except UserProfile.DoesNotExist:
            return False

class CanManageInvoices(permissions.BasePermission):
    """
    Permission to check if user can manage invoices.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        try:
            profile = request.user.profile
            if profile.role == 'VIEWER':
                return request.method in permissions.SAFE_METHODS
            return profile.role in ['ADMIN', 'ACCOUNTANT']
        except UserProfile.DoesNotExist:
            return False

    def has_object_permission(self, request, view, obj):
        try:
            profile = request.user.profile
            # Viewers can only view
            if profile.role == 'VIEWER':
                return request.method in permissions.SAFE_METHODS
            
            # Check specific actions for accountants
            if profile.role == 'ACCOUNTANT':
                if request.method == 'DELETE':
                    return False
                if getattr(view, 'action', None) == 'void':
                    return False
                return True
            
            # Admins have full access
            return profile.role == 'ADMIN'
        except UserProfile.DoesNotExist:
            return False

class CanManageClients(permissions.BasePermission):
    """
    Permission to check if user can manage clients.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        try:
            profile = request.user.profile
            if profile.role == 'VIEWER':
                return request.method in permissions.SAFE_METHODS
            return profile.role in ['ADMIN', 'ACCOUNTANT']
        except UserProfile.DoesNotExist:
            return False

class CanAccessReports(permissions.BasePermission):
    """
    Permission to check if user can access reports.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        try:
            profile = request.user.profile
            return profile.role in ['ADMIN', 'ACCOUNTANT', 'VIEWER']
        except UserProfile.DoesNotExist:
            return False

class CanManageSettings(permissions.BasePermission):
    """
    Permission to check if user can manage company settings.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        try:
            profile = request.user.profile
            if request.method in permissions.SAFE_METHODS:
                return True
            return profile.role == 'ADMIN'
        except UserProfile.DoesNotExist:
            return False

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Instance must have an attribute named `owner`.
        return obj.created_by == request.user

class CanExportData(permissions.BasePermission):
    """
    Permission to check if user can export data.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        try:
            profile = request.user.profile
            return profile.role in ['ADMIN', 'ACCOUNTANT']
        except UserProfile.DoesNotExist:
            return False

class CanManagePayments(permissions.BasePermission):
    """
    Permission to check if user can manage payments.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        try:
            profile = request.user.profile
            if profile.role == 'VIEWER':
                return request.method in permissions.SAFE_METHODS
            return profile.role in ['ADMIN', 'ACCOUNTANT']
        except UserProfile.DoesNotExist:
            return False

    def has_object_permission(self, request, view, obj):
        try:
            profile = request.user.profile
            if profile.role == 'VIEWER':
                return request.method in permissions.SAFE_METHODS
            elif profile.role == 'ACCOUNTANT':
                # Accountants can create and view payments but not delete them
                return request.method != 'DELETE'
            return profile.role == 'ADMIN'
        except UserProfile.DoesNotExist:
            return False