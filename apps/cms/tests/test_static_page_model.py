from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.cms.models import StaticPage, StaticPageBlock


class StaticPageModelTests(TestCase):
    def setUp(self):
        StaticPage.objects.all().delete()

    def test_generates_slug_from_title(self):
        page = StaticPage.objects.create(
            title_ru='About Us',
            content_ru='Company story',
        )

        self.assertEqual(page.slug, 'about-us')
        self.assertEqual(str(page), 'About Us')

    def test_generates_unique_slug_from_duplicate_titles(self):
        StaticPage.objects.create(
            title_ru='Delivery',
            content_ru='First delivery page',
        )
        second = StaticPage.objects.create(
            title_ru='Delivery',
            content_ru='Second delivery page',
        )

        self.assertEqual(second.slug, 'delivery-2')

    def test_title_is_required(self):
        page = StaticPage(slug='privacy-policy', title_ru='   ', content_ru='Privacy content')

        with self.assertRaises(ValidationError) as context:
            page.full_clean()

        self.assertIn('title_ru', context.exception.error_dict)


class StaticPageBlockModelTests(TestCase):
    def setUp(self):
        StaticPage.objects.all().delete()
        self.page = StaticPage.objects.create(title_ru='FAQ')

    def test_blocks_are_ordered_by_sort_order_then_id(self):
        second = StaticPageBlock.objects.create(
            page=self.page,
            title_ru='Второй',
            content_ru='Текст 2',
            sort_order=20,
        )
        first = StaticPageBlock.objects.create(
            page=self.page,
            title_ru='Первый',
            content_ru='Текст 1',
            sort_order=10,
        )

        self.assertEqual(list(self.page.blocks.all()), [first, second])

    def test_block_is_deleted_with_page(self):
        block = StaticPageBlock.objects.create(
            page=self.page,
            title_ru='Вопрос',
            content_ru='Ответ',
        )

        self.page.delete()

        self.assertFalse(StaticPageBlock.objects.filter(pk=block.pk).exists())

