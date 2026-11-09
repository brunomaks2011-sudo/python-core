"""Catalogue and stock models.

Two layers, as on BrickLink:

* reference catalogue – ``Color``, ``Theme``, ``PartCategory``, ``Part``,
  ``Element``, ``LegoSet``, ``Minifigure`` (official LEGO numbers);
* shop listings – ``Product`` (+ ``ProductImage``, ``Inventory``): what the shop
  actually sells, in a given colour and condition, at a given price.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from core.utils import make_slug


class Color(models.Model):
    FINISHES = [
        ("solid", "Звичайний"),
        ("trans", "Прозорий"),
        ("chrome", "Хром"),
        ("pearl", "Перламутровий"),
        ("metallic", "Металік"),
        ("glitter", "З блискітками"),
        ("glow", "Світиться в темряві"),
        ("satin", "Сатиновий / опаловий"),
        ("speckle", "Крапчастий"),
        ("other", "Інший"),
    ]

    name = models.CharField("Офіційна назва", max_length=64, unique=True)
    name_uk = models.CharField("Назва українською", max_length=64, blank=True)
    slug = models.SlugField(max_length=80, unique=True)
    rgb = models.CharField("Колір (HEX)", max_length=6, default="CCCCCC")
    finish = models.CharField("Тип", max_length=12, choices=FINISHES, default="solid")
    is_transparent = models.BooleanField("Прозорий", default=False)
    bricklink_id = models.PositiveIntegerField("BrickLink ID", null=True, blank=True, unique=True)
    rebrickable_id = models.IntegerField("Rebrickable ID", null=True, blank=True, unique=True)
    lego_id = models.PositiveIntegerField("Номер кольору LEGO", null=True, blank=True)
    lego_name = models.CharField("Назва кольору LEGO", max_length=64, blank=True)
    sort_order = models.PositiveIntegerField("Порядок", default=1000)
    is_active = models.BooleanField("Показувати у фільтрах", default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "колір"
        verbose_name_plural = "кольори"

    def __str__(self):
        return self.display_name

    @property
    def display_name(self) -> str:
        return self.name_uk or self.name

    @property
    def hex(self) -> str:
        return f"#{self.rgb}"

    @property
    def code(self) -> str:
        """Colour number shown to customers (BrickLink numbering when known)."""
        if self.bricklink_id is not None:
            return str(self.bricklink_id)
        if self.rebrickable_id is not None:
            return f"RB{self.rebrickable_id}"
        return str(self.pk)

    def get_absolute_url(self):
        return reverse("catalog:color", args=[self.slug])

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_slug(self.name)
        self.rgb = (self.rgb or "CCCCCC").lstrip("#").upper()[:6]
        if self.finish == "trans" or self.name.lower().startswith(("trans", "glitter trans", "opal trans", "satin trans")):
            self.is_transparent = True
        super().save(*args, **kwargs)


class Theme(models.Model):
    """A LEGO series (City, Technic, Star Wars ...)."""

    name = models.CharField("Назва серії", max_length=120)
    title = models.CharField("Назва для показу", max_length=150, blank=True, help_text="Напр. «LEGO Star Wars»")
    slug = models.SlugField(max_length=140, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.SET_NULL,
                               verbose_name="Батьківська серія")
    rebrickable_id = models.PositiveIntegerField(null=True, blank=True, unique=True)
    is_primary = models.BooleanField("Показувати в меню наборів", default=False)
    show_in_minifigs = models.BooleanField("Показувати в меню мініфігурок", default=False)
    accent = models.CharField("Колір акценту", max_length=7, default="#E3000B")
    description = models.TextField("Опис", blank=True)
    sort_order = models.PositiveIntegerField("Порядок", default=100)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "серія LEGO"
        verbose_name_plural = "серії LEGO"

    def __str__(self):
        return self.display_name

    @property
    def display_name(self) -> str:
        return self.title or self.name

    @property
    def short_name(self) -> str:
        return self.display_name.removeprefix("LEGO ").strip()

    def get_absolute_url(self):
        return reverse("catalog:theme", args=[self.slug])

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_slug(self.name)
        super().save(*args, **kwargs)

    def descendant_ids(self) -> list[int]:
        ids, frontier = [self.pk], [self.pk]
        while frontier:
            frontier = list(Theme.objects.filter(parent_id__in=frontier).values_list("pk", flat=True))
            ids.extend(frontier)
        return ids


class Category(models.Model):
    """Shop navigation category (Набори, Деталі → Цеглинки, Мініфігурки ...)."""

    KINDS = [
        ("set", "Набори"),
        ("part", "Деталі"),
        ("minifig", "Мініфігурки"),
        ("keychain", "Брелоки"),
        ("book", "Книги з фігурками"),
        ("accessory", "Аксесуари"),
        ("other", "Інше"),
    ]

    name = models.CharField("Назва", max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.CASCADE,
                               verbose_name="Батьківська категорія")
    kind = models.CharField("Тип товарів", max_length=12, choices=KINDS, default="part")
    description = models.TextField("Опис", blank=True)
    icon = models.CharField("Іконка", max_length=32, blank=True)
    rebrickable_part_categories = models.CharField(
        "Категорії деталей Rebrickable", max_length=255, blank=True,
        help_text="ID категорій через кому – для автоматичного розподілу деталей при імпорті")
    sort_order = models.PositiveIntegerField("Порядок", default=100)
    is_active = models.BooleanField("Активна", default=True)
    seo_title = models.CharField("SEO-заголовок", max_length=160, blank=True)
    seo_description = models.CharField("SEO-опис", max_length=300, blank=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "категорія"
        verbose_name_plural = "категорії"

    def __str__(self):
        return f"{self.parent.name} › {self.name}" if self.parent_id else self.name

    def get_absolute_url(self):
        return reverse("catalog:category", args=[self.slug])

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_slug(self.name)
        super().save(*args, **kwargs)

    def descendant_ids(self) -> list[int]:
        ids, frontier = [self.pk], [self.pk]
        while frontier:
            frontier = list(Category.objects.filter(parent_id__in=frontier).values_list("pk", flat=True))
            ids.extend(frontier)
        return ids

    def rb_category_ids(self) -> list[int]:
        return [int(x) for x in self.rebrickable_part_categories.replace(" ", "").split(",") if x.isdigit()]


class PartCategory(models.Model):
    """Reference part category from the official catalogue (Rebrickable numbering)."""

    id = models.PositiveIntegerField(primary_key=True)
    name = models.CharField(max_length=160)

    class Meta:
        ordering = ["name"]
        verbose_name = "тип деталі (каталог)"
        verbose_name_plural = "типи деталей (каталог)"

    def __str__(self):
        return self.display_name

    @property
    def display_name(self) -> str:
        from .structure import PART_CATEGORY_UK

        return PART_CATEGORY_UK.get(self.name, self.name)


class Part(models.Model):
    design_id = models.CharField("Номер деталі (Design ID)", max_length=40, unique=True)
    name = models.CharField("Офіційна назва", max_length=255)
    name_uk = models.CharField("Назва українською", max_length=255, blank=True)
    part_category = models.ForeignKey(PartCategory, null=True, blank=True, on_delete=models.SET_NULL,
                                      verbose_name="Тип за каталогом")
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL,
                                 verbose_name="Категорія магазину", related_name="parts")
    alternate_ids = models.CharField("Альтернативні номери", max_length=255, blank=True,
                                     help_text="Через кому, напр. 3068, 3068a")
    description = models.TextField("Опис", blank=True)

    class Meta:
        ordering = ["design_id"]
        verbose_name = "деталь (каталог)"
        verbose_name_plural = "деталі (каталог)"

    def __str__(self):
        return f"{self.design_id} {self.display_name}"

    @property
    def display_name(self) -> str:
        return self.name_uk or self.name


class Element(models.Model):
    """LEGO Element ID – one design in one colour."""

    element_id = models.CharField("Element ID", max_length=20, unique=True)
    part = models.ForeignKey(Part, related_name="elements", on_delete=models.CASCADE, verbose_name="Деталь")
    color = models.ForeignKey(Color, related_name="elements", on_delete=models.CASCADE, verbose_name="Колір")

    class Meta:
        ordering = ["element_id"]
        verbose_name = "елемент (Element ID)"
        verbose_name_plural = "елементи (Element ID)"
        indexes = [models.Index(fields=["part", "color"])]

    def __str__(self):
        return self.element_id


class LegoSet(models.Model):
    number = models.CharField("Номер набору", max_length=40, unique=True, help_text="Напр. 75355-1")
    name = models.CharField("Офіційна назва", max_length=255)
    theme = models.ForeignKey(Theme, null=True, blank=True, on_delete=models.SET_NULL, related_name="sets",
                              verbose_name="Серія")
    year = models.PositiveSmallIntegerField("Рік випуску", null=True, blank=True)
    pieces = models.PositiveIntegerField("Кількість деталей", null=True, blank=True)
    minifigs_count = models.PositiveSmallIntegerField("Кількість мініфігурок", null=True, blank=True)
    age_min = models.PositiveSmallIntegerField("Вік від", null=True, blank=True,
                                               validators=[MaxValueValidator(99)])
    height_cm = models.DecimalField("Висота моделі, см", max_digits=6, decimal_places=1, null=True, blank=True)
    width_cm = models.DecimalField("Ширина моделі, см", max_digits=6, decimal_places=1, null=True, blank=True)
    depth_cm = models.DecimalField("Глибина моделі, см", max_digits=6, decimal_places=1, null=True, blank=True)
    image_url = models.URLField("Зображення (каталог)", blank=True)

    class Meta:
        ordering = ["number"]
        verbose_name = "набір (каталог)"
        verbose_name_plural = "набори (каталог)"
        indexes = [models.Index(fields=["year"])]

    def __str__(self):
        return f"{self.base_number} {self.name}"

    @property
    def base_number(self) -> str:
        """75355-1 -> 75355 (variant suffix is kept when it is not -1)."""
        num, _, var = self.number.partition("-")
        return num if var in ("", "1") else self.number

    @property
    def dimensions(self) -> str:
        dims = [d for d in (self.height_cm, self.width_cm, self.depth_cm) if d]
        if len(dims) != 3:
            return ""
        return " × ".join(f"{d.normalize():f}".replace(".", ",") for d in dims) + " см"


class Minifigure(models.Model):
    fig_number = models.CharField("Номер фігурки", max_length=40, unique=True,
                                  help_text="Номер у каталозі (напр. fig-000123)")
    bricklink_id = models.CharField("Номер BrickLink", max_length=40, blank=True, db_index=True,
                                    help_text="Напр. sw0001 – якщо відомий")
    name = models.CharField("Офіційна назва", max_length=255)
    character = models.CharField("Персонаж", max_length=160, blank=True)
    theme = models.ForeignKey(Theme, null=True, blank=True, on_delete=models.SET_NULL, related_name="minifigures",
                              verbose_name="Серія")
    year = models.PositiveSmallIntegerField("Рік", null=True, blank=True)
    num_parts = models.PositiveSmallIntegerField("Кількість частин", null=True, blank=True)
    image_url = models.URLField("Зображення (каталог)", blank=True)
    contents = models.JSONField("Комплектація", default=list, blank=True,
                                help_text='Список {"part": "...", "name": "...", "color": "...", "qty": 1}')
    appears_in = models.JSONField("Входить до наборів", default=list, blank=True)

    class Meta:
        ordering = ["fig_number"]
        verbose_name = "мініфігурка (каталог)"
        verbose_name_plural = "мініфігурки (каталог)"

    def __str__(self):
        return f"{self.display_number} {self.name}"

    @property
    def display_number(self) -> str:
        return self.bricklink_id or self.fig_number


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def in_stock(self):
        return self.filter(inventory__quantity__gt=0)

    def with_related(self):
        return self.select_related(
            "lego_set", "part", "color", "minifigure", "theme", "category", "inventory"
        ).prefetch_related("images")


class Product(models.Model):
    KIND_SET, KIND_PART, KIND_MINIFIG, KIND_ACCESSORY, KIND_OTHER = "set", "part", "minifig", "accessory", "other"
    KIND_KEYCHAIN, KIND_BOOK = "keychain", "book"
    KINDS = [
        (KIND_SET, "Набір"),
        (KIND_PART, "Деталь"),
        (KIND_MINIFIG, "Мініфігурка"),
        (KIND_KEYCHAIN, "Брелок"),
        (KIND_BOOK, "Книга з фігуркою"),
        (KIND_ACCESSORY, "Аксесуар"),
        (KIND_OTHER, "Інше"),
    ]
    # kinds that may include a minifigure (a minifigure keychain, a book with a figure)
    WITH_FIGURE = {KIND_KEYCHAIN, KIND_BOOK}
    CONDITION_NEW, CONDITION_USED = "new", "used"
    CONDITIONS = [(CONDITION_NEW, "Новий"), (CONDITION_USED, "Б/у")]
    SKU_PREFIX = {KIND_SET: "S", KIND_PART: "P", KIND_MINIFIG: "M", KIND_KEYCHAIN: "K", KIND_BOOK: "B",
                  KIND_ACCESSORY: "A", KIND_OTHER: "X"}

    kind = models.CharField("Тип", max_length=12, choices=KINDS, default=KIND_SET, db_index=True)
    sku = models.CharField("Артикул магазину", max_length=60, unique=True, blank=True,
                           help_text="Залиште порожнім – згенерується автоматично")
    title = models.CharField("Назва", max_length=255, blank=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    lego_set = models.ForeignKey(LegoSet, null=True, blank=True, on_delete=models.PROTECT, related_name="products",
                                 verbose_name="Набір")
    part = models.ForeignKey(Part, null=True, blank=True, on_delete=models.PROTECT, related_name="products",
                             verbose_name="Деталь")
    color = models.ForeignKey(Color, null=True, blank=True, on_delete=models.PROTECT, related_name="products",
                              verbose_name="Колір")
    minifigure = models.ForeignKey(Minifigure, null=True, blank=True, on_delete=models.PROTECT,
                                   related_name="products", verbose_name="Мініфігурка")
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="products", verbose_name="Категорія")
    theme = models.ForeignKey(Theme, null=True, blank=True, on_delete=models.SET_NULL, related_name="products",
                              verbose_name="Серія")
    condition = models.CharField("Стан", max_length=8, choices=CONDITIONS, default=CONDITION_NEW, db_index=True)
    completeness = models.CharField("Комплектація / примітка до стану", max_length=255, blank=True)
    price = models.DecimalField("Ціна, ₴", max_digits=10, decimal_places=2,
                                validators=[MinValueValidator(Decimal("0.01"))])
    old_price = models.DecimalField("Стара ціна, ₴", max_digits=10, decimal_places=2, null=True, blank=True,
                                    help_text="Вкажіть, щоб показати знижку")
    description = models.TextField("Опис", blank=True)
    is_active = models.BooleanField("Показувати на сайті", default=True, db_index=True)
    is_featured = models.BooleanField("Популярний (головна)", default=False)
    is_bestseller = models.BooleanField("Хіт продажів", default=False)
    is_new = models.BooleanField("Новинка", default=False)
    is_rare = models.BooleanField("Рідкісний / колекційний", default=False)
    views_count = models.PositiveIntegerField("Перегляди", default=0)
    sold_count = models.PositiveIntegerField("Продано", default=0)
    rating_avg = models.DecimalField("Рейтинг", max_digits=3, decimal_places=2, default=0)
    reviews_count = models.PositiveIntegerField("Відгуків", default=0)
    search_text = models.TextField(blank=True, editable=False)
    created_at = models.DateTimeField("Додано", default=timezone.now, db_index=True)
    updated_at = models.DateTimeField("Оновлено", auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "товар"
        verbose_name_plural = "товари"
        indexes = [
            models.Index(fields=["kind", "is_active"]),
            models.Index(fields=["price"]),
            models.Index(fields=["sold_count"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["part", "color", "condition"], condition=Q(kind="part"), name="unique_part_color_condition"
            ),
        ]

    def __str__(self):
        return f"{self.sku} {self.title}"

    # ----- derived data -------------------------------------------------
    @property
    def official_number(self) -> str:
        if self.kind == self.KIND_PART and self.part_id:
            return self.part.design_id
        if self.kind == self.KIND_MINIFIG and self.minifigure_id:
            return self.minifigure.display_number
        if self.lego_set_id:
            return self.lego_set.base_number
        return ""

    @property
    def number_label(self) -> str:
        return {
            self.KIND_PART: "Design ID",
            self.KIND_MINIFIG: "Номер фігурки",
            self.KIND_SET: "Номер набору",
        }.get(self.kind, "Номер LEGO")

    @property
    def element_id(self) -> str:
        if self.kind != self.KIND_PART or not (self.part_id and self.color_id):
            return ""
        el = getattr(self, "_element_cache", None)
        if el is None:
            el = Element.objects.filter(part_id=self.part_id, color_id=self.color_id).values_list(
                "element_id", flat=True).first() or ""
            self._element_cache = el
        return el

    @property
    def stock(self) -> int:
        inv = getattr(self, "inventory", None)
        return inv.quantity if inv else 0

    @property
    def in_stock(self) -> bool:
        return self.stock > 0

    @property
    def low_stock(self) -> bool:
        threshold = settings.SHOP["LOW_STOCK_THRESHOLD"]
        return 0 < self.stock <= threshold and self.kind != self.KIND_PART

    @property
    def discount_percent(self) -> int:
        if self.old_price and self.old_price > self.price:
            return int(round((1 - self.price / self.old_price) * 100))
        return 0

    @property
    def main_image(self):
        images = getattr(self, "_prefetched_objects_cache", {}).get("images")
        if images is None:
            return self.images.first()
        return images[0] if images else None

    @property
    def max_order_quantity(self) -> int:
        return self.stock

    @property
    def pieces(self):
        return self.lego_set.pieces if self.lego_set_id else None

    @property
    def year(self):
        if self.lego_set_id:
            return self.lego_set.year
        if self.minifigure_id:
            return self.minifigure.year
        return None

    def get_absolute_url(self):
        return reverse("catalog:product", args=[self.slug])

    # ----- saving -------------------------------------------------------
    def default_title(self) -> str:
        if self.kind == self.KIND_PART and self.part_id:
            return self.part.display_name
        if self.kind == self.KIND_MINIFIG and self.minifigure_id:
            return self.minifigure.name
        if self.lego_set_id:
            return self.lego_set.name
        return self.title or "Товар"

    def generate_sku(self) -> str:
        prefix = self.SKU_PREFIX.get(self.kind, "X")
        cond = "U" if self.condition == self.CONDITION_USED else "N"
        if self.kind == self.KIND_PART and self.part_id:
            core = f"{self.part.design_id}-{self.color.code if self.color_id else '0'}"
        elif self.kind == self.KIND_MINIFIG and self.minifigure_id:
            core = self.minifigure.display_number
        elif self.lego_set_id:
            core = self.lego_set.base_number
        else:
            core = make_slug(self.title)[:20].upper() or "ITEM"
        base = f"BH-{prefix}-{core}-{cond}".upper()
        sku, n = base, 2
        while Product.objects.filter(sku=sku).exclude(pk=self.pk).exists():
            sku, n = f"{base}-{n}", n + 1
        return sku

    def generate_slug(self) -> str:
        if self.kind == self.KIND_PART and self.part_id:
            parts = [self.part.design_id, self.part.name, self.color.name if self.color_id else ""]
        elif self.kind == self.KIND_MINIFIG and self.minifigure_id:
            parts = [self.minifigure.display_number, self.minifigure.name]
        elif self.lego_set_id:
            parts = ["lego", self.theme.short_name if self.theme_id else "", self.lego_set.base_number,
                     self.lego_set.name]
        else:
            parts = [self.title]
        if self.condition == self.CONDITION_USED:
            parts.append("vzhyvanyi")
        base = make_slug(*parts, max_length=180)
        slug, n = base, 2
        while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug, n = f"{base}-{n}", n + 1
        return slug

    def build_search_text(self) -> str:
        bits = [self.sku, self.title, self.get_kind_display(), self.get_condition_display()]
        if self.lego_set_id:
            s = self.lego_set
            bits += [s.number, s.base_number, s.name]
        if self.part_id:
            p = self.part
            bits += [p.design_id, p.name, p.name_uk, p.alternate_ids.replace(",", " ")]
            if self.color_id:
                bits += list(Element.objects.filter(part=p, color_id=self.color_id).values_list("element_id", flat=True))
        if self.color_id:
            c = self.color
            bits += [c.name, c.name_uk, c.lego_name]
        if self.minifigure_id:
            m = self.minifigure
            bits += [m.fig_number, m.bricklink_id, m.name, m.character]
        if self.theme_id:
            bits += [self.theme.name, self.theme.title]
        if self.category_id:
            bits += [self.category.name]
        return " ".join(str(b) for b in bits if b).lower()

    def save(self, *args, **kwargs):
        if not self.title:
            self.title = self.default_title()
        if self.kind == self.KIND_SET and self.lego_set_id and not self.theme_id:
            self.theme_id = self.lego_set.theme_id
        if self.kind == self.KIND_MINIFIG and self.minifigure_id and not self.theme_id:
            self.theme_id = self.minifigure.theme_id
        if not self.sku:
            self.sku = self.generate_sku()
        if not self.slug:
            self.slug = self.generate_slug()
        self.search_text = self.build_search_text()
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating:
            Inventory.objects.get_or_create(product=self)

    def refresh_rating(self):
        agg = self.reviews.filter(is_published=True).aggregate(avg=models.Avg("rating"), n=models.Count("id"))
        self.rating_avg = Decimal(str(round(agg["avg"] or 0, 2)))
        self.reviews_count = agg["n"]
        Product.objects.filter(pk=self.pk).update(rating_avg=self.rating_avg, reviews_count=self.reviews_count)


def product_image_path(instance, filename):
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "jpg").lower()
    return f"products/{timezone.now():%Y/%m}/{instance.product.sku.lower()}-{timezone.now():%H%M%S%f}.{ext}"


class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField("Фото", upload_to=product_image_path, blank=True)
    thumbnail = models.ImageField(upload_to="products/thumbs/", blank=True, editable=False)
    external_url = models.URLField("Посилання на зображення", blank=True, max_length=500)
    alt = models.CharField("Підпис (alt)", max_length=255, blank=True)
    sort_order = models.PositiveIntegerField("Порядок", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "фото товару"
        verbose_name_plural = "фото товарів"

    def __str__(self):
        return self.alt or f"Фото {self.pk}"

    @property
    def url(self) -> str:
        if self.image:
            return self.image.url
        return self.external_url

    @property
    def thumb_url(self) -> str:
        if self.thumbnail:
            return self.thumbnail.url
        return self.url

    def save(self, *args, **kwargs):
        new_file = bool(self.image) and not self.thumbnail
        super().save(*args, **kwargs)
        if new_file:
            from .images import process_upload

            if process_upload(self):
                super().save(update_fields=["image", "thumbnail"])


class Inventory(models.Model):
    product = models.OneToOneField(Product, related_name="inventory", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField("Кількість на складі", default=0)
    location = models.CharField("Місце на складі", max_length=64, blank=True, help_text="Напр. A-03-12")
    low_stock_threshold = models.PositiveIntegerField("Поріг «закінчується»", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "складський залишок"
        verbose_name_plural = "складські залишки"

    def __str__(self):
        return f"{self.product.sku}: {self.quantity}"

    @classmethod
    def from_db(cls, db, field_names, values):
        obj = super().from_db(db, field_names, values)
        obj._loaded_quantity = obj.quantity
        return obj

    def save(self, *args, **kwargs):
        was = getattr(self, "_loaded_quantity", None)
        super().save(*args, **kwargs)
        self._loaded_quantity = self.quantity
        if was == 0 and self.quantity > 0:
            from .notifications import notify_back_in_stock

            product_id = self.product_id
            transaction.on_commit(lambda: notify_back_in_stock(product_id))


class InventoryMovement(models.Model):
    REASONS = [
        ("order", "Замовлення"),
        ("cancel", "Скасування замовлення"),
        ("manual", "Ручна зміна"),
        ("import", "Імпорт"),
        ("restock", "Надходження"),
        ("return", "Повернення"),
    ]
    inventory = models.ForeignKey(Inventory, related_name="movements", on_delete=models.CASCADE)
    change = models.IntegerField("Зміна")
    quantity_after = models.PositiveIntegerField("Залишок після")
    reason = models.CharField("Причина", max_length=12, choices=REASONS, default="manual")
    note = models.CharField("Примітка", max_length=255, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    order = models.ForeignKey("orders.Order", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "рух товару"
        verbose_name_plural = "рух товарів"


class Review(models.Model):
    product = models.ForeignKey(Product, related_name="reviews", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="reviews", on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField("Оцінка", validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField("Заголовок", max_length=120, blank=True)
    text = models.TextField("Відгук", max_length=3000)
    is_published = models.BooleanField("Опубліковано", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "відгук"
        verbose_name_plural = "відгуки"
        constraints = [models.UniqueConstraint(fields=["product", "user"], name="one_review_per_user")]

    def __str__(self):
        return f"{self.product.title}: {self.rating}★"


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="favorites", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name="favorited_by", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "обране"
        verbose_name_plural = "обране"
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="unique_favorite")]


class StockNotification(models.Model):
    product = models.ForeignKey(Product, related_name="stock_notifications", on_delete=models.CASCADE)
    email = models.EmailField("E-mail")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "запит на повідомлення"
        verbose_name_plural = "повідомлення про надходження"
        constraints = [
            models.UniqueConstraint(fields=["product", "email"], condition=Q(notified_at__isnull=True),
                                    name="unique_pending_notification"),
        ]

    def __str__(self):
        return f"{self.email} → {self.product.sku}"
