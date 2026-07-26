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
            title_ru='Homepage hero',
            image=self.make_image_file(),
            button_text_ru='Shop now',
            link='/catalog/',
            sort_order=10,
        )

        self.assertEqual(str(banner), 'Homepage hero')
        self.assertTrue(banner.image.name.startswith('banners/'))
        self.assertEqual(banner.button_text_ru, 'Shop now')
        self.assertTrue(banner.is_active)

    def test_accepts_gif_and_video_for_desktop_and_mobile(self):
        banner = Banner(
            title_ru='Video hero',
            image=SimpleUploadedFile('hero.mp4', b'video content', content_type='video/mp4'),
            image_mobile=SimpleUploadedFile('hero-mobile.gif', b'gif content', content_type='image/gif'),
        )

        banner.full_clean()

        self.assertEqual(banner.image_type, 'video')
        self.assertEqual(banner.image_mobile_type, 'image')

    def test_rejects_unsupported_banner_media(self):
        banner = Banner(
            title_ru='Audio banner',
            image=SimpleUploadedFile('banner.mp3', b'audio content', content_type='audio/mpeg'),
        )

        with self.assertRaises(ValidationError):
            banner.full_clean()

    def test_link_allows_internal_path_or_absolute_url(self):
        internal = Banner(title_ru='Internal', image=self.make_image_file('internal.jpg'), link='/catalog/')
        external = Banner(title_ru='External', image=self.make_image_file('external.jpg'), link='https://example.com/sale')

        internal.full_clean()
        external.full_clean()

    def test_link_rejects_invalid_value(self):
        banner = Banner(title_ru='Invalid', image=self.make_image_file(), link='catalog')

        with self.assertRaises(ValidationError) as context:
            banner.full_clean()

        self.assertIn('link', context.exception.error_dict)

    def test_ends_at_cannot_be_before_starts_at(self):
        now = timezone.now()
        banner = Banner(
            title_ru='Invalid dates',
            image=self.make_image_file(),
            starts_at=now,
            ends_at=now - timedelta(days=1),
        )

        with self.assertRaises(ValidationError) as context:
            banner.full_clean()

        self.assertIn('ends_at', context.exception.error_dict)
