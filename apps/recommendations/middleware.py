import hashlib
import uuid

from django.conf import settings


def hash_anonymous_id(raw_id):
    value = f'{settings.SECRET_KEY}:{raw_id}'.encode('utf-8')
    return hashlib.sha256(value).hexdigest()


class RecommendationAnonymousActorMiddleware:
    """Issue an opaque analytics cookie and expose only its hash to application code."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cookie_name = settings.RECOMMENDATION_ANONYMOUS_COOKIE_NAME
        raw_id = request.COOKIES.get(cookie_name)
        created = False
        try:
            raw_id = str(uuid.UUID(str(raw_id)))
        except (TypeError, ValueError, AttributeError):
            raw_id = str(uuid.uuid4())
            created = True

        request.recommendation_anonymous_id_hash = hash_anonymous_id(raw_id)
        response = self.get_response(request)
        if created and request.path.startswith('/api/'):
            response.set_cookie(
                cookie_name,
                raw_id,
                max_age=settings.RECOMMENDATION_ANONYMOUS_COOKIE_AGE,
                httponly=True,
                secure=not settings.DEBUG,
                samesite='Lax',
            )
        return response
