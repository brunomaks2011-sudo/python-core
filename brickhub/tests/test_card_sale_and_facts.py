"""Product cards as on lego.com: a discount is a red tag beside the price, age and pieces come with icons."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from catalog.models import LegoSet, Minifigure, Product

from .factories import base_catalog, minifig_product, part_product, set_product


class CardSaleAndFactsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()

    def setUp(self):
        self.set = set_product(price="1700")
        Product.objects.filter(pk=self.set.pk).update(old_price=Decimal("2100"), is_new=False)
        LegoSet.objects.filter(pk=self.set.lego_set_id).update(age_min=10, pieces=218)

    def listing(self, slug="nabory"):
        return self.client.get(reverse("catalog:category", args=[slug])).content.decode()

    @staticmethod
    def badges(html):
        return html.split('class="card-badges"')[1].split("</div>")[0]

    def test_discount_is_a_tag_beside_the_old_price(self):
        html = self.listing()
        self.assertIn('<span class="price-was"><s>2 100<span class="cur">&nbsp;₴</span></s>'
                      '<span class="sale-tag">−19%</span></span>', html)
        self.assertIn('<div class="price is-sale">', html)
        self.assertNotIn("%", self.badges(html))  # no longer on the photo

    def test_product_page_puts_the_tag_beside_the_price(self):
        html = self.client.get(self.set.get_absolute_url()).content.decode()
        self.assertIn('<s>2 100 ₴</s><span class="sale-tag">−19%</span>', html)
        self.assertNotIn("pdx-flag is-sale", html)

    def test_no_tag_without_a_discount(self):
        Product.objects.filter(pk=self.set.pk).update(old_price=None)
        html = self.listing()
        self.assertNotIn("sale-tag", html)
        self.assertNotIn("is-sale", html)

    def test_bestseller_label_stays_on_a_discounted_set(self):
        Product.objects.filter(pk=self.set.pk).update(is_bestseller=True)
        self.assertIn("Хіт", self.badges(self.listing()))

    def test_age_and_pieces_with_a_cake_and_a_brick(self):
        html = self.listing()
        self.assertIn('<use href="#i-age"/></svg><span class="sr-only">Вік </span>10+</span>', html)
        self.assertIn('<use href="#i-piece"/></svg><span class="sr-only">Деталей </span>218</span>', html)
        self.assertIn("№ 75355", html)
        # the age is not in the catalogue: no cake, nothing made up
        LegoSet.objects.filter(pk=self.set.lego_set_id).update(age_min=None)
        html = self.listing()
        self.assertNotIn("#i-age", html)
        self.assertIn("#i-piece", html)

    def test_minifigure_shows_its_parts_and_a_part_shows_neither(self):
        fig = minifig_product()
        Minifigure.objects.filter(pk=fig.minifigure_id).update(num_parts=4)
        html = self.listing("minifihurky")
        self.assertIn('<span class="sr-only">Деталей </span>4</span>', html)
        self.assertNotIn("#i-age", html)
        part_product(design="3001", color=self.colors["red"])
        parts = self.listing("detali")
        self.assertNotIn("#i-piece", parts)
        self.assertNotIn("#i-age", parts)
