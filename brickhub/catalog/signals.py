from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Category, Color, Review, Theme


@receiver([post_save, post_delete], sender=Category)
@receiver([post_save, post_delete], sender=Theme)
def reset_nav(sender, **kwargs):
    cache.delete("nav:v1")


@receiver([post_save, post_delete], sender=Color)
def reset_colors(sender, **kwargs):
    cache.delete("search:colors")


@receiver(post_delete, sender=Review)
def review_deleted(sender, instance, **kwargs):
    from .models import Product

    product = Product.objects.filter(pk=instance.product_id).first()
    if product:
        product.refresh_rating()
