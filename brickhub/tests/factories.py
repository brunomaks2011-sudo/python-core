"""Tiny fixture helpers for tests (no external factory library needed)."""
from decimal import Decimal

from catalog.models import Category, Color, Element, Inventory, LegoSet, Minifigure, Part, Product, Theme
from catalog.structure import apply_structure


def base_catalog():
    """Colours with real BrickLink/Rebrickable ids, a series, shop categories."""
    red = Color.objects.create(name="Red", name_uk="Червоний", slug="red", rgb="C91A09", bricklink_id=5,
                               rebrickable_id=4)
    black = Color.objects.create(name="Black", name_uk="Чорний", slug="black", rgb="05131D", bricklink_id=11,
                                 rebrickable_id=0)
    clear = Color.objects.create(name="Trans-Clear", name_uk="Прозорий", slug="trans-clear", rgb="FCFCFC",
                                 bricklink_id=12, rebrickable_id=47)
    Theme.objects.create(name="Star Wars", slug="star-wars-src", rebrickable_id=158)
    Theme.objects.create(name="City", slug="city-src", rebrickable_id=52)
    apply_structure()
    return {"red": red, "black": black, "clear": clear}


def part_product(design="3001", name="Brick 2 x 4", name_uk="Цеглинка 2 × 4", color=None, qty=100,
                 price="6.00", condition="new", element=None):
    cat = Category.objects.get(slug="tsehlynky")
    part, _ = Part.objects.get_or_create(design_id=design, defaults={"name": name, "name_uk": name_uk,
                                                                     "category": cat})
    if element:
        Element.objects.create(element_id=element, part=part, color=color)
    p = Product.objects.create(kind="part", part=part, color=color, condition=condition, price=Decimal(price),
                               category=cat)
    Inventory.objects.filter(product=p).update(quantity=qty)
    p.refresh_from_db()
    return p


def set_product(number="75355-1", name="X-Wing Starfighter", year=2023, pieces=1949, qty=5, price="8999",
                condition="new", theme_slug="star-wars"):
    theme = Theme.objects.get(slug=theme_slug)
    s, _ = LegoSet.objects.get_or_create(number=number, defaults={"name": name, "year": year, "pieces": pieces,
                                                                  "theme": theme, "minifigs_count": 1})
    p = Product.objects.create(kind="set", lego_set=s, condition=condition, price=Decimal(price),
                               category=Category.objects.get(slug="nabory"), theme=theme)
    Inventory.objects.filter(product=p).update(quantity=qty)
    p.refresh_from_db()
    return p


def minifig_product(number="fig-000001", name="Toy Store Employee", qty=3, price="199"):
    fig, _ = Minifigure.objects.get_or_create(fig_number=number, defaults={"name": name})
    p = Product.objects.create(kind="minifig", minifigure=fig, price=Decimal(price),
                               category=Category.objects.get(slug="minifihurky"))
    Inventory.objects.filter(product=p).update(quantity=qty)
    p.refresh_from_db()
    return p
