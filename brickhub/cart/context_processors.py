from django.utils.functional import SimpleLazyObject

from .services import cart_count, compare_ids, favorite_ids


def cart(request):
    if request.path.startswith(("/static/", "/media/", "/img/")):
        return {}
    return {
        "cart_count": SimpleLazyObject(lambda: cart_count(request)),
        "favorite_ids": SimpleLazyObject(lambda: favorite_ids(request)),
        "compare_ids": SimpleLazyObject(lambda: compare_ids(request)),
    }
