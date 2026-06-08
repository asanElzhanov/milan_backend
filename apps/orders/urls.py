from django.urls import path
from . import views

urlpatterns = [
    # Cart
    path('cart/', views.CartView.as_view(), name='cart'),
    path('cart/add/', views.CartAddView.as_view(), name='cart-add'),
    path('cart/items/<int:pk>/', views.CartItemUpdateView.as_view(), name='cart-item-update'),
    path('cart/items/<int:pk>/delete/', views.CartItemDeleteView.as_view(), name='cart-item-delete'),
    path('cart/clear/', views.CartClearView.as_view(), name='cart-clear'),

    # Orders
    path('', views.OrderCreateView.as_view(), name='order-create'),
    path('history/', views.OrderListView.as_view(), name='order-list'),
    path('<str:number>/', views.OrderDetailView.as_view(), name='order-detail'),
]
