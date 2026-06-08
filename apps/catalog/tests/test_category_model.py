from django.test import TestCase

from apps.catalog.models import Category


class CategoryModelTests(TestCase):
    def test_category_slug_is_generated_from_name_when_empty(self):
        category = Category.objects.create(name='Winter Shoes')

        self.assertEqual(category.slug, 'winter-shoes')

    def test_category_active_queryset_returns_only_active_categories(self):
        active = Category.objects.create(name='Active', slug='active')
        Category.objects.create(name='Hidden', slug='hidden', is_active=False)

        self.assertEqual(list(Category.objects.active()), [active])

    def test_category_mptt_tree_fields_are_populated(self):
        root = Category.objects.create(name='Shoes', slug='shoes')
        child = Category.objects.create(name='Sneakers', slug='sneakers', parent=root)

        root.refresh_from_db()
        child.refresh_from_db()

        self.assertEqual(root.level, 0)
        self.assertEqual(child.level, 1)
        self.assertEqual(child.parent, root)
        self.assertIn(child, root.get_children())
