import stripe
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Sum
from datetime import datetime
from .models import Company, Client, Invoice, Expense

stripe.api_key = settings.STRIPE_SECRET_KEY

@login_required
def dashboard(request):
    company = get_object_or_404(Company, owner=request.user)
    total_invoices = Invoice.objects.filter(company=company).count()
    pending_amount = Invoice.objects.filter(
        company=company, 
        status__in=['SENT', 'OVERDUE']
    ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0

    current_month = datetime.now().month
    monthly_expenses = Expense.objects.filter(
        company=company,
        date__month=current_month
    ).aggregate(Sum('amount'))['amount__sum'] or 0

    context = {
        'total_invoices': total_invoices,
        'pending_amount': pending_amount,
        'monthly_expenses': monthly_expenses,
        'company': company,
    }
    return render(request, 'financial_app/dashboard.html', context)

def create_subscription(request):
    if request.method == 'POST':
        user = request.user
        try:
            customer = stripe.Customer.create(email=user.email)
            subscription = stripe.Subscription.create(
                customer=customer.id,
                items=[{"price": "your-stripe-price-id"}],
            )
            return redirect('dashboard')
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    return render(request, 'financial_app/subscribe.html')

@login_required
def upload_receipt(request):
    if request.method == 'POST' and request.FILES['receipt']:
        receipt_image = request.FILES['receipt']
        expense = Expense.objects.create(
            company=request.user.company,
            category=request.POST['category'],
            amount=request.POST['amount'],
            date=request.POST['date'],
            description=request.POST['description'],
            receipt=receipt_image,
        )
        extracted_text = expense.extract_text_from_receipt()
        expense.description += f"\\nExtracted text: {extracted_text}"
        expense.save()
        return redirect('dashboard')
    return render(request, 'financial_app/upload_receipt.html')
