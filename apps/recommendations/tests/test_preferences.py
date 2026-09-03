from django.test import TestCase

from apps.recommendations.constants import EventSource, EventType
from apps.recommendations.models import UserCategoryPreference, UserProductEvent
from apps.recommendations.services import UserPreferenceService

from .factories import make_category, make_product, make_user


class PreferenceTests(TestCase):
    def test_parent_receives_thirty_percent_and_negative_events_subtract(self):
        user = make_user()
        parent = make_category()
        child = make_category(parent=parent)
        product = make_product(category=child)
        UserProductEvent.objects.create(
            user=user, product=product, event_type=EventType.PURCHASE, source=EventSource.ORDER,
        )
        UserPreferenceService.rebuild_user(user.id)
        child_pref = UserCategoryPreference.objects.get(user=user, category=child)
        parent_pref = UserCategoryPreference.objects.get(user=user, category=parent)
        self.assertAlmostEqual(float(parent_pref.score), float(child_pref.score) * 0.3, places=6)

        UserProductEvent.objects.create(
            user=user, product=product, event_type=EventType.RETURN, source=EventSource.ORDER,
        )
        UserPreferenceService.rebuild_user(user.id)
        updated = UserCategoryPreference.objects.get(user=user, category=child)
        self.assertGreater(updated.negative_score, 0)

    def test_rebuild_empty_user_is_idempotent(self):
        user = make_user()
        self.assertEqual(UserPreferenceService.rebuild_user(user.id), 0)
        self.assertEqual(UserPreferenceService.rebuild_user(user.id), 0)

