"""A listing can belong to two series and is shown and found in both."""
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import Product, Theme

from .factories import base_catalog, minifig_product, set_product


class SecondSeriesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        base_catalog()
        cls.star_wars = Theme.objects.get(slug="star-wars")
        cls.city = Theme.objects.get(slug="city")
        cls.xwing = set_product()                       # LEGO Star Wars
        Product.objects.filter(pk=cls.xwing.pk).update(theme2=cls.city)
        cls.xwing.refresh_from_db()
        cls.xwing.save()                                # refresh the search index
        cls.staff = User.objects.create_user("series@example.com", "Correct-horse-1", is_staff=True)

    def test_shown_in_both_series(self):
        for theme in (self.star_wars, self.city):
            self.assertContains(self.client.get(theme.get_absolute_url()), "X-Wing Starfighter")
        listing = self.client.get(reverse("catalog:category", args=["nabory"]) + "?theme=city")
        self.assertContains(listing, "X-Wing Starfighter")
        facet = {t["value"]: t["count"] for t in self.client.get(reverse("catalog:index")).context["listing"].facets["theme"]}
        self.assertEqual((facet["star-wars"], facet["city"]), (1, 1))
        page = self.client.get(self.xwing.get_absolute_url()).content.decode()
        self.assertIn(self.city.get_absolute_url(), page)
        self.assertIn("Серії", page)
        self.assertIn(self.xwing, list(Product.objects.filter(search_text__icontains="city")))

    def test_second_series_in_the_panel(self):
        fig = minifig_product()
        self.client.force_login(self.staff)
        r = self.client.post(reverse("panel:product_edit", args=[fig.pk]), {
            "kind": "minifig", "condition": "new", "fig_number": "fig-000001", "price": "199", "quantity": 3,
            "theme": self.star_wars.pk, "theme2": self.city.pk, "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        fig.refresh_from_db()
        self.assertEqual((fig.theme, fig.theme2), (self.star_wars, self.city))
        self.client.post(reverse("panel:product_edit", args=[fig.pk]), {
            "kind": "minifig", "condition": "new", "fig_number": "fig-000001", "price": "199", "quantity": 3,
            "theme": self.city.pk, "theme2": self.city.pk, "is_active": "on"})
        fig.refresh_from_db()
        self.assertEqual((fig.theme, fig.theme2), (self.city, None))  # the same series twice is kept once
