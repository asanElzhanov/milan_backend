from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.cms.models import StaticPage


class StaticPageAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email='cms-admin@example.com',
            password='secret123',
        )
        self.client.force_login(self.admin_user)
        self.page = StaticPage.objects.create(
            title='Privacy Policy',
            content='Privacy content',
        )

    def test_static_page_changelist_opens(self):
        response = self.client.get(reverse('admin:cms_staticpage_changelist'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Privacy Policy')

    def test_static_page_change_page_opens(self):
        response = self.client.get(reverse('admin:cms_staticpage_change', args=[self.page.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Privacy Policy')
