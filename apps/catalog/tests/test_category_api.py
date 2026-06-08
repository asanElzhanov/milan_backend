from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Category


class CategoryAPITests(APITestCase):
    list_url = '/api/v1/catalog/categories/'
    tree_url = '/api/v1/catalog/categories/tree/'

    def setUp(self):
        self.root = Category.objects.create(
            name='Shoes',
            slug='shoes',
            sort_order=1,
            seo_title='Shoes SEO',
            seo_description='Shoes description',
            seo_keywords='shoes,sneakers',
        )
        self.child = Category.objects.create(
            name='Sneakers',
            slug='sneakers',
            parent=self.root,
            sort_order=1,
        )
        self.inactive_root = Category.objects.create(
            name='Archive',
            slug='archive',
            is_active=False,
            sort_order=2,
        )
        self.inactive_child = Category.objects.create(
            name='Hidden',
            slug='hidden',
            parent=self.root,
            is_active=False,
            sort_order=2,
        )

    def detail_url(self, category):
        return f'/api/v1/catalog/categories/{category.slug}/'

    def response_items(self, response):
        return response.data['results'] if isinstance(response.data, dict) else response.data

    def test_category_list_returns_flat_categories(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = self.response_items(response)
        slugs = {item['slug'] for item in items}
        self.assertEqual(slugs, {'shoes', 'sneakers', 'archive', 'hidden'})
        self.assertNotIn('children', items[0])

    def test_category_list_filters_active_categories(self):
        response = self.client.get(self.list_url, {'active': 'true'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {item['slug'] for item in self.response_items(response)}
        self.assertEqual(slugs, {'shoes', 'sneakers'})

    def test_category_list_filters_inactive_categories(self):
        response = self.client.get(self.list_url, {'active': 'false'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {item['slug'] for item in self.response_items(response)}
        self.assertEqual(slugs, {'archive', 'hidden'})

    def test_category_list_filters_by_parent(self):
        response = self.client.get(self.list_url, {'parent': self.root.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {item['slug'] for item in self.response_items(response)}
        self.assertEqual(slugs, {'sneakers', 'hidden'})

    def test_category_tree_returns_nested_categories(self):
        response = self.client.get(self.tree_url, {'active': 'true'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = self.response_items(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['slug'], 'shoes')
        self.assertEqual([child['slug'] for child in items[0]['children']], ['sneakers'])

    def test_category_detail_by_slug_returns_category(self):
        response = self.client.get(self.detail_url(self.root))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.root.id)
        self.assertEqual(response.data['slug'], 'shoes')
        self.assertEqual(response.data['parent'], None)
        self.assertEqual(response.data['seo_title'], 'Shoes SEO')
        self.assertEqual(response.data['seo_description'], 'Shoes description')
        self.assertEqual(response.data['seo_keywords'], 'shoes,sneakers')
        self.assertIn('children', response.data)
