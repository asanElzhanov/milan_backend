from django.urls import path
from . import views

urlpatterns = [
    path('categories/', views.CategoryListView.as_view(), name='categories'),
    path('categories/tree/', views.CategoryTreeView.as_view(), name='category-tree'),
    path('categories/<slug:slug>/', views.CategoryDetailView.as_view(), name='category-detail'),
    path('brands/', views.BrandListView.as_view(), name='brands'),
    path('brands/<slug:slug>/', views.BrandDetailView.as_view(), name='brand-detail'),
    path('colors/', views.ColorListView.as_view(), name='colors'),
    path('sizes/', views.SizeListView.as_view(), name='sizes'),

    path('stock/', views.StockVariantListView.as_view(), name='stock-list'),
    path('stock/adjust/', views.StockAdjustmentView.as_view(), name='stock-adjust'),
    path('stock/movements/', views.StockMovementListView.as_view(), name='stock-movements'),

    path('products/', views.ProductListView.as_view(), name='product-list'),
    path('products/<slug:slug>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('products/<slug:slug>/similar/', views.ProductSimilarView.as_view(), name='product-similar'),
    path('products/<slug:slug>/reviews/', views.ProductReviewListView.as_view(), name='product-reviews'),
    path('reviews/', views.ReviewCreateView.as_view(), name='review-create'),

    path('banners/', views.BannerListView.as_view(), name='banners'),
    path('promo/check/', views.PromoCheckView.as_view(), name='promo-check'),
]
