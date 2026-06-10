from decimal import Decimal
import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.catalog.models import Brand, Category, Product, ProductMedia


class ProductMediaModelTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

        category = Category.objects.create(name='Shoes', slug='shoes')
        brand = Brand.objects.create(name='Nike', slug='nike')
        self.product = Product.objects.create(
            sku='SKU-MEDIA',
            name='Air Max',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_accepts_video_url(self):
        media = ProductMedia(
            product=self.product,
            media_type=ProductMedia.MediaType.VIDEO,
            url='https://example.com/video.mp4',
            title='Runway video',
        )

        media.full_clean()

    def test_accepts_file_for_optional_image_media(self):
        media = ProductMedia(
            product=self.product,
            media_type=ProductMedia.MediaType.IMAGE,
            file=SimpleUploadedFile('detail.jpg', b'image content', content_type='image/jpeg'),
            alt_text='Detail shot',
        )

        media.full_clean()

    def test_requires_file_or_url(self):
        media = ProductMedia(
            product=self.product,
            media_type=ProductMedia.MediaType.VIDEO,
        )

        with self.assertRaises(ValidationError):
            media.full_clean()

    def test_rejects_unknown_media_type(self):
        media = ProductMedia(
            product=self.product,
            media_type='audio',
            url='https://example.com/audio.mp3',
        )

        with self.assertRaises(ValidationError):
            media.full_clean()
