from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Color


class ColorAPITests(APITestCase):
    list_url = '/api/v1/catalog/colors/'

    def setUp(self):
        self.black = Color.objects.create(name='Black', slug='black', hex_code='#000000')
        self.white = Color.objects.create(name='White', slug='white', hex_code='#FFFFFF')
        self.archive = Color.objects.create(
            name='Archive',
            slug='archive',
            hex_code='#ABCDEF',
            is_active=False,
        )

    def response_items(self, response):
        return response.data['results'] if isinstance(response.data, dict) else response.data

    def test_color_hex_code_accepts_valid_hex_value(self):
        color = Color(name='Blue', slug='blue', hex_code='#3366FF')

        color.full_clean()

    def test_color_hex_code_rejects_invalid_hex_value(self):
        color = Color(name='Broken', slug='broken', hex_code='3366FF')

        with self.assertRaises(ValidationError):
            color.full_clean()

    def test_color_slug_is_generated_from_name_when_empty(self):
        color = Color.objects.create(name='Light Blue', hex_code='#ADD8E6')

        self.assertEqual(color.slug, 'light-blue')

    def test_color_list_returns_colors_ordered_by_name(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [item['name'] for item in self.response_items(response)]
        self.assertEqual(names, ['Archive', 'Black', 'White'])

    def test_color_list_filters_active_colors(self):
        response = self.client.get(self.list_url, {'active': 'true'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {item['slug'] for item in self.response_items(response)}
        self.assertEqual(slugs, {'black', 'white'})

    def test_color_list_filters_inactive_colors(self):
        response = self.client.get(self.list_url, {'active': 'false'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {item['slug'] for item in self.response_items(response)}
        self.assertEqual(slugs, {'archive'})
