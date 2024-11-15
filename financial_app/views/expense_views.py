from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Count
from django.core.paginator import Paginator
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied
import csv
import io

from ..models import (
    Expense, ExpenseCategory, Company
)
from ..forms import (
    ExpenseCreateForm, ExpenseBulkUploadForm,
    ExpenseFilterForm, ExpenseCategoryForm
)
from ..services.expense_service import ExpenseService

@login_required
def expense_list(request):
    """
    Display list of expenses with filtering and sorting options.
    """
    company = get_object_or_404(Company, owner=request.user)
    
    # Initialize filter form
    filter_form = ExpenseFilterForm(request.GET)
    expenses = Expense.objects.filter(company=company).select_related('category')
    
    # Apply filters if form is valid
    if filter_form.is_valid():
        filters = filter_form.cleaned_data
        
        if filters.get('date_from'):
            expenses = expenses.filter(date__gte=filters['date_from'])
        
        if filters.get('date_to'):
            expenses = expenses.filter(date__lte=filters['date_to'])
        
        if filters.get('category'):
            expenses = expenses.filter(category=filters['category'])
        
        if filters.get('min_amount'):
            expenses = expenses.filter(amount__gte=filters['min_amount'])
        
        if filters.get('max_amount'):
            expenses = expenses.filter(amount__lte=filters['max_amount'])
        
        if filters.get('vendor'):
            expenses = expenses.filter(vendor__icontains=filters['vendor'])
        
        if filters.get('payment_method'):
            expenses = expenses.filter(payment_method=filters['payment_method'])
        
        if filters.get('tax_deductible'):
            tax_filter = filters['tax_deductible'] == 'yes'
            expenses = expenses.filter(tax_deductible=tax_filter)

    # Apply sorting
    sort_by = request.GET.get('sort_by', '-date')
    expenses = expenses.order_by(sort_by)

    # Pagination
    paginator = Paginator(expenses, 25)
    page = request.GET.get('page')
    expenses_page = paginator.get_page(page)

    # Calculate summary metrics
    summary = {
        'total_amount': expenses.aggregate(total=Sum('amount'))['total'] or 0,
        'count': expenses.count(),
        'tax_deductible_amount': expenses.filter(
            tax_deductible=True
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'pending_approval': expenses.filter(
            approved_by__isnull=True
        ).count()
    }

    context = {
        'expenses': expenses_page,
        'filter_form': filter_form,
        'summary': summary,
        'categories': ExpenseCategory.objects.filter(is_active=True),
        'payment_methods': dict(Expense.PAYMENT_METHOD_CHOICES)
    }

    return render(request, 'financial_app/expenses/list.html', context)

@login_required
@transaction.atomic
def expense_create(request):
    """
    Create a new expense record.
    """
    company = get_object_or_404(Company, owner=request.user)
    
    if request.method == 'POST':
        form = ExpenseCreateForm(
            request.POST, 
            request.FILES,
            company=company
        )
        
        if form.is_valid():
            try:
                expense = form.save(commit=False)
                expense.company = company
                expense.created_by = request.user
                expense.save()
                
                messages.success(request, _("Expense recorded successfully"))
                return redirect('expense_detail', pk=expense.pk)
                
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = ExpenseCreateForm(
            company=company,
            initial={'date': timezone.now().date()}
        )

    context = {
        'form': form,
        'company': company
    }

    return render(request, 'financial_app/expenses/create.html', context)

@login_required
def expense_detail(request, pk):
    """
    Display expense details.
    """
    expense = get_object_or_404(
        Expense.objects.select_related('category', 'company', 'created_by', 'approved_by'),
        pk=pk,
        company__owner=request.user
    )

    context = {
        'expense': expense,
        'can_edit': not expense.approved_by,
        'can_approve': request.user.profile.role in ['ADMIN', 'ACCOUNTANT']
    }

    return render(request, 'financial_app/expenses/detail.html', context)

@login_required
@transaction.atomic
def expense_update(request, pk):
    """
    Update an existing expense record.
    """
    expense = get_object_or_404(
        Expense,
        pk=pk,
        company__owner=request.user
    )

    if expense.approved_by:
        messages.error(request, _("Cannot modify approved expenses"))
        return redirect('expense_detail', pk=expense.pk)

    if request.method == 'POST':
        form = ExpenseCreateForm(
            request.POST,
            request.FILES,
            instance=expense,
            company=expense.company
        )
        
        if form.is_valid():
            try:
                form.save()
                messages.success(request, _("Expense updated successfully"))
                return redirect('expense_detail', pk=expense.pk)
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = ExpenseCreateForm(
            instance=expense,
            company=expense.company
        )

    context = {
        'form': form,
        'expense': expense
    }

    return render(request, 'financial_app/expenses/update.html', context)

@login_required
@permission_required('financial_app.can_approve_expenses')
def expense_approve(request, pk):
    """
    Approve an expense record.
    """
    expense = get_object_or_404(
        Expense,
        pk=pk,
        company__owner=request.user
    )

    if expense.approved_by:
        messages.error(request, _("Expense is already approved"))
        return redirect('expense_detail', pk=expense.pk)

    try:
        ExpenseService.approve_expense(expense, request.user)
        messages.success(request, _("Expense approved successfully"))
    except Exception as e:
        messages.error(request, str(e))

    return redirect('expense_detail', pk=expense.pk)

@login_required
@transaction.atomic
def expense_bulk_upload(request):
    """
    Handle bulk upload of expenses via CSV/Excel file.
    """
    company = get_object_or_404(Company, owner=request.user)

    if request.method == 'POST':
        form = ExpenseBulkUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                uploaded_file = request.FILES['file']
                date_format = form.cleaned_data['date_format']
                category_mapping = form.cleaned_data['category_mapping']

                result = ExpenseService.process_bulk_upload(
                    company,
                    uploaded_file,
                    date_format,
                    category_mapping,
                    request.user
                )

                messages.success(
                    request,
                    _("Successfully uploaded %(count)d expenses") % {
                        'count': result['success_count']
                    }
                )

                if result['error_count']:
                    messages.warning(
                        request,
                        _("%(count)d expenses failed to upload. Check the error log.") % {
                            'count': result['error_count']
                        }
                    )

                return redirect('expense_list')

            except Exception as e:
                messages.error(request, str(e))
    else:
        form = ExpenseBulkUploadForm()

    context = {
        'form': form,
        'template_url': '/static/templates/expense_upload_template.xlsx'
    }

    return render(request, 'financial_app/expenses/bulk_upload.html', context)

@login_required
def expense_export(request):
    """
    Export expenses to CSV.
    """
    company = get_object_or_404(Company, owner=request.user)
    
    # Get filtered queryset
    filter_form = ExpenseFilterForm(request.GET)
    expenses = Expense.objects.filter(company=company).select_related('category')
    
    if filter_form.is_valid():
        filters = filter_form.cleaned_data
        # Apply same filters as in list view
        # [Previous filter logic here]

    # Create CSV file
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow([
        'Date', 'Category', 'Amount', 'Vendor', 'Description',
        'Payment Method', 'Reference Number', 'Tax Deductible'
    ])

    # Write data
    for expense in expenses:
        writer.writerow([
            expense.date.strftime('%Y-%m-%d'),
            expense.category.name,
            str(expense.amount),
            expense.vendor,
            expense.description,
            expense.get_payment_method_display(),
            expense.reference_number,
            'Yes' if expense.tax_deductible else 'No'
        ])

    # Create response
    response = HttpResponse(output.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="expenses.csv"'
    
    return response

@login_required
def expense_category_manage(request):
    """
    Manage expense categories.
    """
    if request.method == 'POST':
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, _("Category created successfully"))
                return redirect('expense_category_manage')
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = ExpenseCategoryForm()

    categories = ExpenseCategory.objects.all().order_by('name')
    
    context = {
        'form': form,
        'categories': categories
    }

    return render(request, 'financial_app/expenses/categories.html', context)