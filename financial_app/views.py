# financial_app/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Sum
from .models import Company, Client, Invoice, Expense
from datetime import datetime

@login_required
def dashboard(request):
    try:
        company = Company.objects.get(owner=request.user)
    except Company.DoesNotExist:
        # Redirect to a page where the user can create a Company or show an appropriate message
        return render(request, 'financial_app/no_company.html')

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
        # Handle invoice creation logic
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
        # Handle receipt upload logic
        pass
    return render(request, 'financial_app/upload_receipt.html')

def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'financial_app/signup.html', {'form': form})

@login_required
def client_list(request):
    clients = Client.objects.filter(company__owner=request.user)
    return render(request, 'financial_app/client_list.html', {'clients': clients})

@login_required
def add_client(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.company = request.user.company  # Ensure client is linked to the user's company
            client.save()
            return redirect('client_list')  # Redirect back to the client list
    else:
        form = ClientForm()

    return render(request, 'financial_app/add_client.html', {'form': form})
