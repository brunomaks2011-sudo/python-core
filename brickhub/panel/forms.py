from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Case, Q, When

from cart.models import PromoCode
from catalog.images import validate_image_file
from catalog.models import Category, category_tree, Color, Element, LegoSet, Minifigure, Part, Product, Theme
from orders.models import Order

from .owners import owner_name


class SearchableSelect(forms.Select):
    """A normal <select>; app.js turns it into a field where you can type to search."""

    def __init__(self, attrs=None, choices=()):
        super().__init__({**(attrs or {}), "data-searchable": "1"}, choices)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        obj = getattr(value, "instance", None)
        if isinstance(obj, Color):
            option["attrs"]["data-hex"] = obj.hex
            option["attrs"]["data-search"] = " ".join(
                str(x) for x in (obj.name, obj.name_uk, obj.lego_name, obj.bricklink_id, obj.rebrickable_id)
                if x not in (None, ""))
        elif isinstance(obj, Theme):
            option["attrs"]["data-search"] = f"{obj.name} {obj.title}"
        elif isinstance(obj, Category):
            option["attrs"]["data-search"] = f"{obj.name} {obj.slug}"
            option["attrs"]["data-kind"] = obj.kind
        return option


class ColorChoiceField(forms.ModelChoiceField):
    """Colour choices labelled «Лавандовий (Lavender) · 154» (Ukrainian, official name, BrickLink number)."""

    def label_from_instance(self, obj):
        label = obj.display_name
        if obj.name_uk and obj.name_uk != obj.name:
            label += f" ({obj.name})"
        return f"{label} · {obj.code}"


class ProductForm(forms.ModelForm):
    """Create / edit a listing. LEGO numbers are checked against the catalogue."""

    color = ColorChoiceField(label="Колір", queryset=Color.objects.none(), required=False, widget=SearchableSelect,
                             help_text="Почніть вводити назву українською чи англійською або номер кольору")
    set_number = forms.CharField(label="Номер LEGO", required=False, max_length=40,
                                 help_text="Номер з каталогу LEGO. Для аксесуарів, брелоків і книг — необов'язково")
    design_id = forms.CharField(label="Design ID деталі", required=False, max_length=40)
    fig_number = forms.CharField(label="Номер мініфігурки", required=False, max_length=40,
                                 help_text="Номер каталогу (fig-000123) або BrickLink (sw0001). Для брелока чи "
                                           "книги — фігурка в комплекті, необов'язково")
    element_id = forms.CharField(label="Element ID", required=False, max_length=20,
                                 help_text="Необов'язково: офіційний номер елемента LEGO для цього кольору")
    create_catalog = forms.BooleanField(
        label="Номера немає в каталозі — створити запис вручну", required=False,
        help_text="Лише для нових офіційних позицій, яких ще немає в довіднику. Вкажіть офіційну назву.")
    official_name = forms.CharField(label="Офіційна назва (для нового запису каталогу)", required=False,
                                    max_length=255)
    quantity = forms.IntegerField(label="Кількість на складі", min_value=0, initial=0)
    location = forms.CharField(label="Місце на складі", required=False, max_length=64)
    # set details (stored on the catalogue entry)
    year = forms.IntegerField(label="Рік випуску", required=False, min_value=1949, max_value=2100)
    pieces = forms.IntegerField(label="Кількість деталей", required=False, min_value=0)
    minifigs_count = forms.IntegerField(label="Кількість мініфігурок", required=False, min_value=0)
    age_min = forms.IntegerField(label="Вік від, років", required=False, min_value=1, max_value=99)
    height_cm = forms.DecimalField(label="Висота, см", required=False, max_digits=6, decimal_places=1)
    width_cm = forms.DecimalField(label="Ширина, см", required=False, max_digits=6, decimal_places=1)
    depth_cm = forms.DecimalField(label="Глибина, см", required=False, max_digits=6, decimal_places=1)
    # minifigure details
    bricklink_id = forms.CharField(label="Номер BrickLink", required=False, max_length=40)
    character = forms.CharField(label="Персонаж", required=False, max_length=160)
    contents = forms.CharField(label="Комплектація (рядок: номер | назва | колір | кількість)", required=False,
                               widget=forms.Textarea(attrs={"rows": 4}))

    class Meta:
        model = Product
        fields = ["kind", "condition", "title", "sku", "color", "category", "theme", "price", "old_price",
                  "completeness", "description", "owner", "is_active", "is_featured", "is_bestseller", "is_new",
                  "is_rare"]
        widgets = {"description": forms.Textarea(attrs={"rows": 6}), "sku": forms.TextInput(
            attrs={"placeholder": "згенерується автоматично"}), "category": SearchableSelect,
            "theme": SearchableSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = False
        self.fields["sku"].required = False
        self.fields["color"].queryset = Color.objects.filter(is_active=True).order_by("sort_order", "name")
        tree = category_tree()
        paths = {c.pk: path for c, _depth, path in tree}
        self.fields["category"].queryset = Category.objects.order_by(
            Case(*[When(pk=c.pk, then=i) for i, (c, _d, _p) in enumerate(tree)], default=len(tree)), "name")
        self.fields["category"].label_from_instance = lambda obj: paths.get(obj.pk, obj.name)
        owner = self.fields["owner"]
        owner.queryset = get_user_model().objects.filter(
            Q(is_staff=True) | Q(pk=self.instance.owner_id or 0)).order_by("-is_superuser", "pk")
        owner.label_from_instance = lambda u: f"{owner_name(u)} ({'власник магазину' if u.is_superuser else u.email})"
        owner.empty_label = "— не вказано —"
        owner.help_text = "Для статистики: хто скільки продав"
        self.fields["theme"].queryset = Theme.objects.filter(
            Q(parent__isnull=True) | Q(products__isnull=False)).distinct().order_by("-is_primary", "sort_order", "name")
        p = self.instance
        if p.pk:
            self.fields["quantity"].initial = p.stock
            self.fields["location"].initial = p.inventory.location if hasattr(p, "inventory") else ""
            if p.lego_set_id:
                s = p.lego_set
                self.fields["set_number"].initial = s.base_number
                for f in ("year", "pieces", "minifigs_count", "age_min", "height_cm", "width_cm", "depth_cm"):
                    self.fields[f].initial = getattr(s, f)
            if p.part_id:
                self.fields["design_id"].initial = p.part.design_id
                self.fields["element_id"].initial = p.element_id
            if p.minifigure_id:
                m = p.minifigure
                self.fields["fig_number"].initial = m.fig_number
                self.fields["bricklink_id"].initial = m.bricklink_id
                self.fields["character"].initial = m.character
                self.fields["contents"].initial = "\n".join(
                    f"{c.get('part', '')} | {c.get('name', '')} | {c.get('color', '')} | {c.get('qty', 1)}"
                    for c in (m.contents or []))

    def clean_sku(self):
        sku = (self.cleaned_data.get("sku") or "").strip().upper()
        if sku and Product.objects.filter(sku=sku).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Такий артикул уже існує")
        return sku

    def clean(self):
        data = super().clean()
        kind = data.get("kind")
        create = data.get("create_catalog")
        official = (data.get("official_name") or "").strip()
        self.lego_set = self.part = self.minifigure = None
        if kind in ("set", "accessory", Product.KIND_KEYCHAIN, Product.KIND_BOOK) and data.get("set_number"):
            num = data["set_number"].strip()
            full = num if "-" in num else f"{num}-1"
            self.lego_set = LegoSet.objects.filter(number__iexact=full).first()
            if not self.lego_set:
                if create and official:
                    self.lego_set = LegoSet(number=full, name=official)
                else:
                    self.add_error("set_number", "Такого номера немає в каталозі LEGO. Перевірте номер або "
                                                 "позначте «створити запис вручну» та вкажіть офіційну назву.")
        elif kind == "set":
            self.add_error("set_number", "Вкажіть номер набору")
        if kind == "part":
            design = (data.get("design_id") or "").strip()
            if not design:
                self.add_error("design_id", "Вкажіть Design ID")
            else:
                self.part = Part.objects.filter(design_id__iexact=design).first()
                if not self.part:
                    if create and official:
                        self.part = Part(design_id=design, name=official)
                    else:
                        self.add_error("design_id", "Такої деталі немає в каталозі. Перевірте номер або позначте "
                                                    "«створити запис вручну».")
            if not data.get("color"):
                self.add_error("color", "Для деталі обов'язково вкажіть колір")
            el = (data.get("element_id") or "").strip()
            if el and self.part and data.get("color"):
                clash = Element.objects.filter(element_id=el).exclude(part__design_id=self.part.design_id,
                                                                      color=data["color"]).first()
                if clash:
                    self.add_error("element_id", f"Element ID {el} вже належить {clash.part.design_id} "
                                                 f"({clash.color.name})")
            if self.part and self.part.pk and data.get("color"):
                dup = Product.objects.filter(kind="part", part=self.part, color=data["color"],
                                             condition=data.get("condition")).exclude(pk=self.instance.pk).first()
                if dup:
                    self.add_error(None, f"Ця деталь у цьому кольорі та стані вже є: {dup.sku}. Змініть кількість "
                                         "у наявному товарі.")
        if kind == "minifig":
            num = (data.get("fig_number") or "").strip()
            if not num:
                self.add_error("fig_number", "Вкажіть номер мініфігурки")
            else:
                self.minifigure = (Minifigure.objects.filter(fig_number__iexact=num).first()
                                   or Minifigure.objects.filter(bricklink_id__iexact=num).first())
                if not self.minifigure:
                    if create and official:
                        self.minifigure = Minifigure(fig_number=num, name=official)
                    else:
                        self.add_error("fig_number", "Такої мініфігурки немає в каталозі. Перевірте номер або "
                                                     "позначте «створити запис вручну».")
        elif kind in Product.WITH_FIGURE and (data.get("fig_number") or "").strip():
            num = data["fig_number"].strip()
            self.minifigure = (Minifigure.objects.filter(fig_number__iexact=num).first()
                               or Minifigure.objects.filter(bricklink_id__iexact=num).first())
            if not self.minifigure:
                self.add_error("fig_number", "Такої мініфігурки немає в каталозі. Перевірте номер або залиште "
                                             "поле порожнім.")
        if kind in ("accessory", "other", Product.KIND_KEYCHAIN, Product.KIND_BOOK) and not data.get("title") \
                and not self.lego_set:
            self.add_error("title", "Вкажіть назву товару")
        return data

    def save(self, commit=True):
        product = super().save(commit=False)
        data = self.cleaned_data
        if self.lego_set is not None:
            s = self.lego_set
            for f in ("year", "pieces", "minifigs_count", "age_min", "height_cm", "width_cm", "depth_cm"):
                if data.get(f) is not None:
                    setattr(s, f, data[f])
            if not s.theme_id and data.get("theme"):
                s.theme = data["theme"]
            s.save()
            product.lego_set = s
        if self.part is not None:
            if not self.part.pk:
                self.part.category = data.get("category")
                self.part.save()
            product.part = self.part
            el = (data.get("element_id") or "").strip()
            if el and data.get("color"):
                Element.objects.update_or_create(element_id=el, defaults={"part": self.part, "color": data["color"]})
        if self.minifigure is not None and product.kind in Product.WITH_FIGURE:
            product.minifigure = self.minifigure  # figure included with a keychain or a book
        elif self.minifigure is not None:
            m = self.minifigure
            m.bricklink_id = data.get("bricklink_id") or m.bricklink_id
            m.character = data.get("character") or m.character
            if data.get("contents"):
                rows = []
                for line in data["contents"].splitlines():
                    bits = [b.strip() for b in line.split("|")]
                    if not bits or not bits[0]:
                        continue
                    qty = int(bits[3]) if len(bits) > 3 and bits[3].isdigit() else 1
                    rows.append({"part": bits[0], "name": bits[1] if len(bits) > 1 else "",
                                 "color": bits[2] if len(bits) > 2 else "", "qty": qty})
                m.contents = rows
            if not m.theme_id and data.get("theme"):
                m.theme = data["theme"]
            m.save()
            product.minifigure = m
        if product.kind != "part":
            product.part = None
        if product.kind == "minifig":
            product.lego_set = None
        if product.kind in Product.WITH_FIGURE | {Product.KIND_ACCESSORY, Product.KIND_OTHER} and \
                not (data.get("set_number") or "").strip():
            product.lego_set = None
        if product.kind not in Product.WITH_FIGURE | {Product.KIND_MINIFIG} or (
                product.kind in Product.WITH_FIGURE and not (data.get("fig_number") or "").strip()):
            product.minifigure = None
        if not product.category_id:
            # put the product into its section automatically (a part into its part category)
            product.category = (product.part.category if product.part_id and product.part.category_id else
                                Category.objects.filter(parent__isnull=True, kind=product.kind).order_by(
                                    "sort_order").first())
        if not product.title:
            product.title = product.default_title()
        product.search_text = ""
        if commit:
            product.save()
            inv = product.inventory
            if inv.quantity != data["quantity"] or inv.location != (data.get("location") or ""):
                from catalog.models import InventoryMovement

                change = data["quantity"] - inv.quantity
                inv.quantity = data["quantity"]
                inv.location = data.get("location") or ""
                inv.save()
                if change:
                    InventoryMovement.objects.create(inventory=inv, change=change, quantity_after=inv.quantity,
                                                     reason="manual", user=getattr(self, "user", None))
        return product


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    # listing the formats makes iPhones send JPEG instead of HEIC
    widget = MultipleFileInput(attrs={"accept": "image/jpeg,image/png,image/webp,image/gif"})

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        cleaned = []
        for f in files[:12]:
            validate_image_file(f)
            cleaned.append(f)
        return cleaned


class ImagesForm(forms.Form):
    images = MultipleImageField(label="Фото (JPG, PNG, WEBP, до 8 МБ, можна кілька)", required=False)
    external_url = forms.URLField(label="…або посилання на зображення", required=False)


class OrderStatusForm(forms.Form):
    status = forms.ChoiceField(label="Новий статус", choices=Order.STATUSES)
    note = forms.CharField(label="Коментар (бачить покупець)", required=False, max_length=500)
    notify = forms.BooleanField(label="Надіслати лист покупцю", required=False, initial=True)


class OrderMetaForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["tracking_number", "delivery_cost", "admin_note"]
        widgets = {"admin_note": forms.Textarea(attrs={"rows": 3})}


class ImportForm(forms.Form):
    KINDS = [("auto", "Визначити автоматично"), ("parts", "Деталі"), ("sets", "Набори"), ("minifigs", "Мініфігурки"),
             ("stock", "Оновлення залишків і цін за артикулом")]
    file = forms.FileField(label="Файл CSV або Excel (.xlsx)")
    kind = forms.ChoiceField(label="Тип даних", choices=KINDS, initial="auto")
    allow_new_catalog = forms.BooleanField(
        label="Дозволити нові записи каталогу (якщо є колонка official_name)", required=False)

    def clean_file(self):
        f = self.cleaned_data["file"]
        if f.size > 25 * 1024 * 1024:
            raise forms.ValidationError("Файл завеликий (максимум 25 МБ)")
        if not f.name.lower().endswith((".csv", ".txt", ".xlsx", ".xlsm")):
            raise forms.ValidationError("Підтримуються файли .csv та .xlsx")
        return f


class UserAdminForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "email", "phone", "is_active", "is_staff"]


# ---- simple catalogue editors (generic CRUD) ----
class ColorForm(forms.ModelForm):
    class Meta:
        model = Color
        fields = ["name", "name_uk", "rgb", "finish", "is_transparent", "bricklink_id", "rebrickable_id", "lego_id",
                  "lego_name", "sort_order", "is_active"]


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "slug", "parent", "kind", "icon", "description", "rebrickable_part_categories",
                  "sort_order", "is_active", "seo_title", "seo_description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "parent": SearchableSelect}


class ThemeForm(forms.ModelForm):
    class Meta:
        model = Theme
        fields = ["name", "title", "slug", "parent", "is_primary", "show_in_minifigs", "accent", "description",
                  "sort_order"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "accent": forms.TextInput(attrs={"type": "color"}),
                   "parent": SearchableSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Theme.objects.filter(parent__isnull=True)


class PartForm(forms.ModelForm):
    class Meta:
        model = Part
        fields = ["design_id", "name", "name_uk", "category", "part_category", "alternate_ids", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "category": SearchableSelect,
                   "part_category": SearchableSelect}


class LegoSetForm(forms.ModelForm):
    class Meta:
        model = LegoSet
        fields = ["number", "name", "theme", "year", "pieces", "minifigs_count", "age_min", "height_cm", "width_cm",
                  "depth_cm", "image_url"]
        widgets = {"theme": SearchableSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["theme"].queryset = Theme.objects.order_by("name")


class MinifigureForm(forms.ModelForm):
    class Meta:
        model = Minifigure
        fields = ["fig_number", "bricklink_id", "name", "character", "theme", "year", "num_parts", "image_url"]
        widgets = {"theme": SearchableSelect}


class ElementForm(forms.ModelForm):
    design_id = forms.CharField(label="Design ID")
    color = ColorChoiceField(label="Колір", queryset=Color.objects.order_by("name"), widget=SearchableSelect)

    class Meta:
        model = Element
        fields = ["element_id", "color"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["design_id"].initial = self.instance.part.design_id

    def clean_design_id(self):
        part = Part.objects.filter(design_id__iexact=self.cleaned_data["design_id"].strip()).first()
        if not part:
            raise forms.ValidationError("Такої деталі немає в каталозі")
        self.instance.part = part
        return part.design_id


class PromoCodeForm(forms.ModelForm):
    class Meta:
        model = PromoCode
        fields = ["code", "description", "discount_type", "value", "scope", "min_order_total", "max_uses",
                  "once_per_user", "valid_from", "valid_to", "is_active"]
        widgets = {"valid_from": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                   "valid_to": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}

    def clean_value(self):
        v = self.cleaned_data["value"]
        if self.cleaned_data.get("discount_type") == PromoCode.TYPE_PERCENT and v > 100:
            raise forms.ValidationError("Відсоток не може бути більшим за 100")
        return v
