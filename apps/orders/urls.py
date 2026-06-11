from django.urls import path
from . import views

urlpatterns = [
    # Cart
    path('cart/', views.CartView.as_view(), name='cart'),
    path('cart/items/', views.CartAddView.as_view(), name='cart-item-create'),
    path('cart/items/<int:pk>/', views.CartItemUpdateView.as_view(), name='cart-item-detail'),
    path('cart/clear/', views.CartClearView.as_view(), name='cart-clear'),
    path('cart/merge/', views.CartMergeView.as_view(), name='cart-merge'),

    # Backward-compatible cart aliases
    path('cart/add/', views.CartAddView.as_view(), name='cart-add'),
    path('cart/items/<int:pk>/delete/', views.CartItemDeleteView.as_view(), name='cart-item-delete'),

    # Orders
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('', views.OrderCreateView.as_view(), name='order-create'),
    path('history/', views.OrderListView.as_view(), name='order-list'),
    path('<str:order_number>/', views.OrderDetailView.as_view(), name='order-detail'),
]
