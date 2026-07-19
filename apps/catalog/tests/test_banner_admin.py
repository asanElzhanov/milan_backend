import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.catalog.models import Banner


class BannerAdminTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.admin_user = User.objects.create_superuser(
            email='banner-admin@example.com',
            password='secret123',
        )
        self.client.force_login(self.admin_user)
        self.banner = Banner.objects.create(
            title_ru='Admin banner',
            subtitle_ru='Season collection',
            image=self.make_image_file(),
            button_text_ru='Shop',
            link='/catalog/',
        )

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def make_image_file(self, name='admin-banner.jpg'):
        return SimpleUploadedFile(
            name,
            b'fake image content',
            content_type='image/jpeg',
        )

    def test_banner_changelist_opens(self):
        response = self.client.get(reverse('admin:catalog_banner_changelist'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin banner')
        self.assertContains(response, 'Season collection')
        self.assertContains(response, '/catalog/')

    def test_banner_change_page_opens(self):
        response = self.client.get(reverse('admin:catalog_banner_change', args=[self.banner.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin banner')
        self.assertContains(response, 'Shop')
