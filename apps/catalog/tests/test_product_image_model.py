from decimal import Decimal
import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.catalog.models import Brand, Category, Product, ProductImage


class ProductImageModelTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

        self.category = Category.objects.create(name_ru='Shoes', slug='shoes')
        self.brand = Brand.objects.create(name_ru='Nike', slug='nike')
        self.product = Product.objects.create(
            sku='SKU-IMAGE',
            name_ru='Air Max',
            category=self.category,
            brand=self.brand,
            price=Decimal('100.00'),
        )

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def make_image_file(self, name='product.jpg'):
        return SimpleUploadedFile(
            name,
            b'fake image content',
            content_type='image/jpeg',
        )

    def test_creates_product_image(self):
        image = ProductImage.objects.create(
            product=self.product,
            image=self.make_image_file(),
            alt_text='Black sneaker side view',
        )

        self.assertEqual(image.product, self.product)
        self.assertTrue(image.image.name.startswith('products/images/'))
        self.assertEqual(image.alt_text, 'Black sneaker side view')

    def test_accepts_gif_and_video_files_and_reports_media_type(self):
        gif = ProductImage(
            product=self.product,
            image=self.make_image_file('animated.gif'),
        )
        video = ProductImage(
            product=self.product,
            image=SimpleUploadedFile('showcase.mp4', b'video content', content_type='video/mp4'),
        )

        gif.full_clean()
        video.full_clean()

        self.assertEqual(gif.media_type, 'image')
        self.assertEqual(video.media_type, 'video')

    def test_rejects_unsupported_media_extension(self):
        media = ProductImage(
            product=self.product,
            image=SimpleUploadedFile('sound.mp3', b'audio content', content_type='audio/mpeg'),
        )

        with self.assertRaises(ValidationError):
            media.full_clean()

    def test_only_one_main_image_per_product(self):
        first = ProductImage.objects.create(
            product=self.product,
            image=self.make_image_file('first.jpg'),
            is_main=True,
        )
        second = ProductImage.objects.create(
            product=self.product,
            image=self.make_image_file('second.jpg'),
            is_main=True,
        )

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertFalse(first.is_main)
        self.assertTrue(second.is_main)
        self.assertEqual(self.product.images.filter(is_main=True).count(), 1)

    def test_orders_images_by_sort_order_then_id(self):
        second = ProductImage.objects.create(
            product=self.product,
            image=self.make_image_file('second.jpg'),
            sort_order=2,
        )
        first = ProductImage.objects.create(
            product=self.product,
            image=self.make_image_file('first.jpg'),
            sort_order=1,
        )
        third = ProductImage.objects.create(
            product=self.product,
            image=self.make_image_file('third.jpg'),
            sort_order=2,
        )

        self.assertEqual(list(self.product.images.all()), [first, second, third])

    def test_alt_text_is_saved(self):
        image = ProductImage.objects.create(
            product=self.product,
            image=self.make_image_file(),
            alt_text='Front view for SEO',
        )

        self.assertEqual(image.alt_text, 'Front view for SEO')
