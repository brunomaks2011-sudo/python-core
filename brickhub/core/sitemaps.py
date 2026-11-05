from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from catalog.filters import COLLECTIONS
from catalog.models import Category, Part, Product, Theme


class StaticSitemap(Sitemap):
    priority = 0.6
    changefreq = "weekly"

    def items(self):
        return ["core:home", "catalog:index", "catalog:part_finder", "catalog:colors", "core:delivery",
                "core:about", "core:contacts", "core:returns", "core:guide"]

    def location(self, item):
        return reverse(item)


class CollectionSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.6

    def items(self):
        return list(COLLECTIONS)

    def location(self, item):
        return reverse("catalog:collection", args=[item])


class CategorySitemap(Sitemap):
    changefreq = "daily"
    priority = 0.7

    def items(self):
        return Category.objects.filter(is_active=True)


class ThemeSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Theme.objects.filter(products__is_active=True).distinct()


class ProductSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8
    limit = 5000

    def items(self):
        return Product.objects.filter(is_active=True).only("slug", "updated_at").order_by("pk")

    def lastmod(self, obj):
        return obj.updated_at


class PartDesignSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return Part.objects.filter(products__is_active=True).distinct().only("design_id").order_by("design_id")

    def location(self, obj):
        return reverse("catalog:part_design", args=[obj.design_id])


SITEMAPS = {
    "static": StaticSitemap, "collections": CollectionSitemap, "categories": CategorySitemap,
    "series": ThemeSitemap, "products": ProductSitemap, "parts": PartDesignSitemap,
}
