from django.urls import path

from . import views


urlpatterns = [
    path('pages/', views.StaticPageListView.as_view(), name='static-page-list'),
    path('pages/<slug:slug>/', views.StaticPageDetailView.as_view(), name='static-page-detail'),
]
