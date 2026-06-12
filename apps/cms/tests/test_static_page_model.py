from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.cms.models import StaticPage


class StaticPageModelTests(TestCase):
    def test_generates_slug_from_title(self):
        page = StaticPage.objects.create(
            title='About Us',
            content='Company story',
        )

        self.assertEqual(page.slug, 'about-us')
        self.assertEqual(str(page), 'About Us')

    def test_generates_unique_slug_from_duplicate_titles(self):
        StaticPage.objects.create(
            title='Delivery',
            content='First delivery page',
        )
        second = StaticPage.objects.create(
            title='Delivery',
            content='Second delivery page',
        )

        self.assertEqual(second.slug, 'delivery-2')

    def test_title_is_required(self):
        page = StaticPage(slug='privacy-policy', title='   ', content='Privacy content')

        with self.assertRaises(ValidationError) as context:
            page.full_clean()

        self.assertIn('title', context.exception.error_dict)

