from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from decimal import Decimal
import csv
import io

from ..models import Client, Company, Invoice, PaymentRecord
from ..forms import (
    ClientForm, ClientBulkUploadForm, 
    ClientNoteForm, ClientFilterForm
)
from ..services.client_service import ClientService
from ..services.report_service import ReportService

@login_required
def client_list(request):
    """
    Display list of clients with filtering and sorting options.
    """
    company = get_object_or_404(Company, owner=request.user)
    
    # Initialize filter form
    filter_form = ClientFilterForm(request.GET)
    clients = Client.objects.filter(company=company)
    
    # Apply filters if form is valid
    if filter_form.is_valid():
        filters = filter_form.cleaned_data
        
        if filters.get('search'):
            search_query = filters['search']
            clients = clients.filter(
                Q(name__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(vat_number__icontains=search_query)
            )
        
        if filters.get('is_active') is not None:
            clients = clients.filter(is_active=filters['is_active'])
        
        if filters.get('has_overdue'):
            clients = clients.filter(
                invoices__status='OVERDUE'
            ).distinct()
        
        if filters.get('min_balance'):
            clients = clients.annotate(
                balance=Sum('invoices__total_amount') - 
                       Sum('invoices__amount_paid')
            ).filter(balance__gte=filters['min_balance'])
        
        if filters.get('max_balance'):
            clients = clients.annotate(
                balance=Sum('invoices__total_amount') - 
                       Sum('invoices__amount_paid')
            ).filter(balance__lte=filters['max_balance'])

    # Apply sorting
    sort_by = request.GET.get('sort_by', 'name')
    if sort_by == 'balance':
        clients = clients.annotate(
            balance=Sum('invoices__total_amount') - 
                   Sum('invoices__amount_paid')
        ).order_by('-balance')
    elif sort_by == 'last_invoice':
        clients = clients.annotate(
            last_invoice=Max('invoices__issue_date')
        ).order_by('-last_invoice')
    else:
        clients = clients.order_by(sort_by)

    # Pagination
    paginator = Paginator(clients, 25)
    page = request.GET.get('page')
    clients_page = paginator.get_page(page)

    # Calculate summary metrics
    summary = {
        'total_clients': clients.count(),
        'active_clients': clients.filter(is_active=True).count(),
        'total_outstanding': clients.aggregate(
            total=Sum('invoices__total_amount') - 
                  Sum('invoices__amount_paid')
        )['total'] or 0,
        'clients_with_overdue': clients.filter(
            invoices__status='OVERDUE'
        ).distinct().count()
    }

    context = {
        'clients': clients_page,
        'filter_form': filter_form,
        'summary': summary
    }

    return render(request, 'financial_app/clients/list.html', context)

@login_required
@transaction.atomic
def client_create(request):
    """
    Create a new client.
    """
    company = get_object_or_404(Company, owner=request.user)
    
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            try:
                client = form.save(commit=False)
                client.company = company
                client.save()
                
                messages.success(request, _("Client created successfully"))
                return redirect('client_detail', pk=client.pk)
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = ClientForm()

    context = {
        'form': form,
        'company': company
    }

    return render(request, 'financial_app/clients/create.html', context)

@login_required
def client_detail(request, pk):
    """
    Display client details and related information.
    """
    client = get_object_or_404(
        Client.objects.select_related('company'),
        pk=pk,
        company__owner=request.user
    )
    
    # Get client analytics
    analytics = ClientService.get_client_dashboard(client)
    
    # Get recent activity
    recent_invoices = Invoice.objects.filter(
        client=client
    ).order_by('-created_at')[:5]
    
    recent_payments = PaymentRecord.objects.filter(
        invoice__client=client
    ).order_by('-payment_date')[:5]

    context = {
        'client': client,
        'analytics': analytics,
        'recent_invoices': recent_invoices,
        'recent_payments': recent_payments
    }

    return render(request, 'financial_app/clients/detail.html', context)

@login_required
@transaction.atomic
def client_update(request, pk):
    """
    Update existing client information.
    """
    client = get_object_or_404(
        Client,
        pk=pk,
        company__owner=request.user
    )
    
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, _("Client updated successfully"))
                return redirect('client_detail', pk=client.pk)
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = ClientForm(instance=client)

    context = {
        'form': form,
        'client': client
    }

    return render(request, 'financial_app/clients/update.html', context)

@login_required
def client_statement(request, pk):
    """
    Generate and display client statement.
    """
    client = get_object_or_404(
        Client,
        pk=pk,
        company__owner=request.user
    )
    
    start_date = request.GET.get('start_date', timezone.now().date().replace(day=1))
    end_date = request.GET.get('end_date', timezone.now().date())
    
    statement = ReportService.generate_client_statement(
        client,
        start_date,
        end_date
    )
    
    if request.GET.get('format') == 'pdf':
        # Generate PDF statement
        pdf_file = ReportService.generate_statement_pdf(statement)
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="statement_{client.id}.pdf"'
        return response
    
    context = {
        'client': client,
        'statement': statement
    }

    return render(request, 'financial_app/clients/statement.html', context)

@login_required
@transaction.atomic
def client_bulk_upload(request):
    """
    Handle bulk upload of clients via CSV/Excel file.
    """
    company = get_object_or_404(Company, owner=request.user)
    
    if request.method == 'POST':
        form = ClientBulkUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                result = ClientService.process_bulk_upload(
                    company,
                    request.FILES['file'],
                    form.cleaned_data['update_existing']
                )
                
                messages.success(
                    request,
                    _("Successfully imported %(count)d clients") % {
                        'count': result['success_count']
                    }
                )
                
                if result['error_count']:
                    messages.warning(
                        request,
                        _("%(count)d clients failed to import") % {
                            'count': result['error_count']
                        }
                    )
                
                return redirect('client_list')
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = ClientBulkUploadForm()

    context = {
        'form': form,
        'template_url': '/static/templates/client_upload_template.xlsx'
    }

    return render(request, 'financial_app/clients/bulk_upload.html', context)

@login_required
def client_add_note(request, pk):
    """
    Add a note to client record.
    """
    client = get_object_or_404(
        Client,
        pk=pk,
        company__owner=request.user
    )
    
    if request.method == 'POST':
        form = ClientNoteForm(request.POST)
        if form.is_valid():
            try:
                ClientService.add_note(
                    client,
                    form.cleaned_data['note'],
                    form.cleaned_data['private'],
                    request.user
                )
                messages.success(request, _("Note added successfully"))
            except Exception as e:
                messages.error(request, str(e))
    
    return redirect('client_detail', pk=pk)

@login_required
def client_export(request):
    """
    Export clients list to CSV.
    """
    company = get_object_or_404(Company, owner=request.user)
    
    # Get filtered queryset
    filter_form = ClientFilterForm(request.GET)
    clients = Client.objects.filter(company=company)
    
    if filter_form.is_valid():
        # Apply same filters as in list view
        pass

    # Create CSV file
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow([
        'Name', 'Email', 'Phone', 'Address', 'VAT Number',
        'Payment Terms', 'Credit Limit', 'Status'
    ])

    # Write data
    for client in clients:
        writer.writerow([
            client.name,
            client.email,
            client.phone,
            client.address,
            client.vat_number,
            client.payment_terms,
            client.credit_limit,
            'Active' if client.is_active else 'Inactive'
        ])

    # Create response
    response = HttpResponse(output.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="clients.csv"'
    
    return response

@login_required
def client_credit_check(request, pk):
    """
    Perform credit check on client.
    """
    client = get_object_or_404(
        Client,
        pk=pk,
        company__owner=request.user
    )
    
    credit_status = ClientService.check_credit_status(client)
    
    return JsonResponse(credit_status)