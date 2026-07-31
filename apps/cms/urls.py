from django.urls import path

from . import views


urlpatterns = [
    path('pages/', views.StaticPageListView.as_view(), name='static-page-list'),
    path('info-docs/', views.InfoDocListView.as_view(), name='info-doc-list'),
    path('pages/<slug:slug>/', views.StaticPageDetailView.as_view(), name='static-page-detail'),
]
