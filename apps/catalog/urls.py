from django.urls import path
from . import views

urlpatterns = [
    path('categories/', views.CategoryListView.as_view(), name='categories'),
    path('brands/', views.BrandListView.as_view(), name='brands'),

    path('products/', views.ProductListView.as_view(), name='product-list'),
    path('products/<slug:slug>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('products/<slug:slug>/similar/', views.ProductSimilarView.as_view(), name='product-similar'),
    path('products/<slug:slug>/reviews/', views.ReviewListCreateView.as_view(), name='product-reviews'),

    path('banners/', views.BannerListView.as_view(), name='banners'),
    path('promo/check/', views.PromoCheckView.as_view(), name='promo-check'),
]
