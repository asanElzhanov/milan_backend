from datetime import timedelta
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Banner


class BannerAPITests(APITestCase):
    list_url = '/api/v1/catalog/banners/'

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def make_image_file(self, name='banner.jpg'):
        return SimpleUploadedFile(
            name,
            b'fake image content',
            content_type='image/jpeg',
        )

    def make_banner(self, title, **kwargs):
        defaults = {
            'image': self.make_image_file(f'{title}.jpg'),
        }
        defaults.update(kwargs)
        return Banner.objects.create(title_ru=title, **defaults)

    def response_items(self, response):
        return response.data['results'] if isinstance(response.data, dict) else response.data

    def test_banner_list_returns_only_active_visible_banners_ordered(self):
        now = timezone.now()
        second = self.make_banner('Second', sort_order=2)
        first = self.make_banner('First', sort_order=1, button_text_ru='Open', link='/catalog/')
        self.make_banner('Inactive', is_active=False, sort_order=0)
        self.make_banner('Future', starts_at=now + timedelta(days=1), sort_order=0)
        self.make_banner('Expired', ends_at=now - timedelta(days=1), sort_order=0)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = self.response_items(response)
        self.assertEqual([item['id'] for item in items], [first.id, second.id])
        self.assertEqual(items[0]['button_text_ru'], 'Open')
        self.assertEqual(items[0]['link'], '/catalog/')
        self.assertIn('sort_order', items[0])
        self.assertEqual(
            set(items[0].keys()),
            {
                'id',
                'title_ru', 'title_kz', 'title_en',
                'subtitle_ru', 'subtitle_kz', 'subtitle_en',
                'button_text_ru', 'button_text_kz', 'button_text_en',
                'image', 'image_mobile', 'link', 'position', 'sort_order',
            },
        )

    def test_banner_list_filters_by_position(self):
        hero = self.make_banner('Hero', position=Banner.Position.HERO)
        self.make_banner('Promo', position=Banner.Position.PROMO)

        response = self.client.get(self.list_url, {'position': Banner.Position.HERO})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = self.response_items(response)
        self.assertEqual([item['id'] for item in items], [hero.id])
