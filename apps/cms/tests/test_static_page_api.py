from rest_framework import status
from rest_framework.test import APITestCase

from apps.cms.models import StaticPage, StaticPageBlock


class StaticPageAPITests(APITestCase):
    list_url = '/api/v1/cms/pages/'

    def setUp(self):
        StaticPage.objects.all().delete()
        self.page = StaticPage.objects.create(
            title_ru='Privacy Policy',
            slug='privacy-policy',
            content_ru='Privacy content',
            seo_title='Privacy SEO',
            seo_description='Privacy description',
        )
        self.inactive_page = StaticPage.objects.create(
            title_ru='Hidden Terms',
            slug='hidden-terms',
            content_ru='Hidden content',
            is_active=False,
        )

    def detail_url(self, page):
        return f'/api/v1/cms/pages/{page.slug}/'

    def response_items(self, response):
        return response.data['results'] if isinstance(response.data, dict) else response.data

    def test_active_page_is_returned_by_slug(self):
        response = self.client.get(self.detail_url(self.page))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.page.id)
        self.assertEqual(response.data['slug'], 'privacy-policy')
        self.assertEqual(response.data['title_ru'], 'Privacy Policy')
        self.assertEqual(response.data['content_ru'], 'Privacy content')

    def test_inactive_page_is_not_returned_by_slug(self):
        response = self.client.get(self.detail_url(self.inactive_page))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_page_returns_404(self):
        response = self.client.get('/api/v1/cms/pages/missing-page/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_static_page_seo_fields_are_returned(self):
        response = self.client.get(self.detail_url(self.page))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['seo_title'], 'Privacy SEO')
        self.assertEqual(response.data['seo_description'], 'Privacy description')

    def test_page_list_returns_only_active_pages_with_short_fields(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = self.response_items(response)
        self.assertEqual([item['slug'] for item in items], ['privacy-policy'])
        self.assertEqual(set(items[0].keys()), {'id', 'slug', 'title_ru', 'title_kz', 'title_en'})

    def test_detail_returns_only_active_blocks_in_sort_order_with_translations(self):
        later = StaticPageBlock.objects.create(
            page=self.page,
            title_ru='Второй блок',
            title_kz='Екінші блок',
            title_en='Second block',
            content_ru='Второй текст',
            content_kz='Екінші мәтін',
            content_en='Second text',
            sort_order=20,
        )
        earlier = StaticPageBlock.objects.create(
            page=self.page,
            title_ru='Первый блок',
            content_ru='Первый текст',
            sort_order=10,
        )
        StaticPageBlock.objects.create(
            page=self.page,
            title_ru='Скрытый блок',
            content_ru='Скрытый текст',
            sort_order=1,
            is_active=False,
        )

        response = self.client.get(self.detail_url(self.page))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([block['id'] for block in response.data['blocks']], [earlier.id, later.id])
        self.assertEqual(response.data['blocks'][1]['title_kz'], 'Екінші блок')
        self.assertEqual(response.data['blocks'][1]['content_en'], 'Second text')
