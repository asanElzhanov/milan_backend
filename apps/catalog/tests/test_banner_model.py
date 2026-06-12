from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Banner


class BannerModelTests(TestCase):
    def make_image_file(self, name='banner.jpg'):
        return SimpleUploadedFile(
            name,
            b'fake image content',
            content_type='image/jpeg',
        )

    def test_creates_banner_with_required_fields(self):
        banner = Banner.objects.create(
            title='Homepage hero',
            image=self.make_image_file(),
            button_text='Shop now',
            link='/catalog/',
            sort_order=10,
        )

        self.assertEqual(str(banner), 'Homepage hero')
        self.assertTrue(banner.image.name.startswith('banners/'))
        self.assertEqual(banner.button_text, 'Shop now')
        self.assertTrue(banner.is_active)

    def test_link_allows_internal_path_or_absolute_url(self):
        internal = Banner(title='Internal', image=self.make_image_file('internal.jpg'), link='/catalog/')
        external = Banner(title='External', image=self.make_image_file('external.jpg'), link='https://example.com/sale')

        internal.full_clean()
        external.full_clean()

    def test_link_rejects_invalid_value(self):
        banner = Banner(title='Invalid', image=self.make_image_file(), link='catalog')

        with self.assertRaises(ValidationError) as context:
            banner.full_clean()

        self.assertIn('link', context.exception.error_dict)

    def test_ends_at_cannot_be_before_starts_at(self):
        now = timezone.now()
        banner = Banner(
            title='Invalid dates',
            image=self.make_image_file(),
            starts_at=now,
            ends_at=now - timedelta(days=1),
        )

        with self.assertRaises(ValidationError) as context:
            banner.full_clean()

        self.assertIn('ends_at', context.exception.error_dict)
