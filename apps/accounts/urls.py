from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('token/refresh/', views.TokenRefreshAPIView.as_view(), name='token-refresh'),

    # Profile
    path('me/', views.MeView.as_view(), name='me'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change-password'),

    # Addresses
    path('addresses/', views.AddressListCreateView.as_view(), name='address-list'),
    path('addresses/<int:pk>/', views.AddressDetailView.as_view(), name='address-detail'),

    # Wishlist
    path('wishlist/', views.WishlistView.as_view(), name='wishlist'),
    path('wishlist/toggle/<int:product_id>/', views.WishlistToggleView.as_view(), name='wishlist-toggle'),

    # OTP
    path('otp/request/', views.OTPRequestView.as_view(), name='otp-request'),
    path('otp/verify/', views.OTPVerifyView.as_view(), name='otp-verify'),
]
