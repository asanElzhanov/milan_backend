from django.urls import path
from . import views

urlpatterns = [
    path('stripe/create-intent/', views.StripeCreateIntentView.as_view(), name='stripe-intent'),
    path('stripe/webhook/', views.StripeWebhookView.as_view(), name='stripe-webhook'),
    path('kaspi/create/', views.KaspiCreateView.as_view(), name='kaspi-create'),
    path('kaspi/webhook/', views.KaspiWebhookView.as_view(), name='kaspi-webhook'),
]
