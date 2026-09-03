from django.urls import path

from . import views


urlpatterns = [
    path('', views.RecommendationListView.as_view(), name='recommendation-list'),
    path('popular/', views.PopularRecommendationView.as_view(), name='recommendation-popular'),
    path('cart/', views.CartRecommendationView.as_view(), name='recommendation-cart'),
    path('events/', views.RecommendationEventView.as_view(), name='recommendation-events'),
    path(
        'products/<slug:slug>/bought-together/',
        views.BoughtTogetherView.as_view(),
        name='recommendation-bought-together',
    ),
    path(
        'products/<int:product_id>/hide/',
        views.HideRecommendationView.as_view(),
        name='recommendation-hide',
    ),
]
