from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),  # Home/dashboard page
    path('subscribe/', views.create_subscription, name='subscribe'),  # Subscription page
    path('upload-receipt/', views.upload_receipt, name='upload_receipt'),  # Receipt upload page
]
