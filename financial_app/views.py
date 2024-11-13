# financial_app/views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Sum
from .models import Company, Client, Invoice, Expense

@login_required
def dashboard(request):
    company = get_object_or_404(Company, owner=request.user)
    total_invoices = Invoice.objects.filter(company=company).count()
    pending_amount = Invoice.objects.filter(
        company=company, 
        status__in=['SENT', 'OVERDUE']
    ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    monthly_expenses = Expense.objects.filter(
        company=company, 
        date__month=datetime.now().month
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    context = {
        'total_invoices': total_invoices,
        'pending_amount': pending_amount,
        'monthly_expenses': monthly_expenses,
        'company': company,
    }
    return render(request, 'financial_app/dashboard.html', context)

@login_required
def create_invoice(request):
    if request.method == 'POST':
        # handle invoice creation logic
        pass
    clients = Client.objects.filter(company__owner=request.user)
    return render(request, 'financial_app/create_invoice.html', {'clients': clients})

@login_required
def client_list(request):
    clients = Client.objects.filter(company__owner=request.user)
    return render(request, 'financial_app/client_list.html', {'clients': clients})

@login_required
def expense_summary(request):
    company = get_object_or_404(Company, owner=request.user)
    expenses_by_category = Expense.objects.filter(company=company).values('category').annotate(total=Sum('amount'))
    return JsonResponse({'expenses': list(expenses_by_category)})

@login_required
def upload_receipt(request):
    if request.method == 'POST':
        # handle receipt upload logic
        pass
    return render(request, 'financial_app/upload_receipt.html')
