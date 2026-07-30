from rest_framework import serializers

from .models import StaticPage, StaticPageBlock


class StaticPageBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaticPageBlock
        fields = (
            'id',
            'title_ru', 'title_kz', 'title_en',
            'content_ru', 'content_kz', 'content_en',
            'sort_order',
        )


class StaticPageListSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaticPage
        fields = ('id', 'slug', 'title_ru', 'title_kz', 'title_en')


class StaticPageDetailSerializer(serializers.ModelSerializer):
    blocks = StaticPageBlockSerializer(many=True, read_only=True)

    class Meta:
        model = StaticPage
        fields = (
            'id', 'slug',
            'title_ru', 'title_kz', 'title_en',
            'content_ru', 'content_kz', 'content_en',
            'seo_title', 'seo_description',
            'blocks',
        )
