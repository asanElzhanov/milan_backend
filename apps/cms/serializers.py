from rest_framework import serializers

from .models import StaticPage


class StaticPageListSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaticPage
        fields = ('id', 'slug', 'title')


class StaticPageDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaticPage
        fields = (
            'id', 'slug', 'title', 'content',
            'seo_title', 'seo_description',
        )
