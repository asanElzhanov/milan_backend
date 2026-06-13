from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Brand


class BrandAPITests(APITestCase):
    list_url = '/api/v1/catalog/brands/'

    def setUp(self):
        self.nike = Brand.objects.create(name='Nike', slug='nike')
        self.adidas = Brand.objects.create(name='Adidas', slug='adidas')
        self.archive = Brand.objects.create(name='Archive', slug='archive', is_active=False)

    def detail_url(self, brand):
        return f'/api/v1/catalog/brands/{brand.slug}/'

    def response_items(self, response):
        return response.data['results'] if isinstance(response.data, dict) else response.data

    def test_brand_list_returns_brands_ordered_by_name(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [item['name'] for item in self.response_items(response)]
        self.assertEqual(names, ['Adidas', 'Archive', 'Nike'])

    def test_brand_list_filters_active_brands(self):
        response = self.client.get(self.list_url, {'active': 'true'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {item['slug'] for item in self.response_items(response)}
        self.assertEqual(slugs, {'adidas', 'nike'})

    def test_brand_list_filters_inactive_brands(self):
        response = self.client.get(self.list_url, {'active': 'false'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {item['slug'] for item in self.response_items(response)}
        self.assertEqual(slugs, {'archive'})

    def test_brand_detail_by_slug_returns_brand(self):
        response = self.client.get(self.detail_url(self.nike))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.nike.id)
        self.assertEqual(response.data['name'], 'Nike')
        self.assertEqual(response.data['slug'], 'nike')
        self.assertEqual(response.data['is_active'], True)

    def test_brand_detail_does_not_expose_inactive_brand(self):
        response = self.client.get(self.detail_url(self.archive))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_brand_slug_is_generated_from_name_when_empty(self):
        brand = Brand.objects.create(name='New Balance')

        self.assertEqual(brand.slug, 'new-balance')
