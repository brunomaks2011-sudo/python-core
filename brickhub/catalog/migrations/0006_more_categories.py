"""More part categories (slopes, baseplates, minifigure parts, electronics ...) and accessory subcategories.

Only categories are added, and reference catalogue parts (the LEGO parts directory, not shop listings) are
re-linked to the new categories. Shop products are not touched: every listing keeps the category it has.
Names and descriptions of existing categories change only while they still have the original text.

On an empty database (fresh install) this does nothing — ``setup_store`` creates the full structure.
"""
from django.db import migrations

# slug, name, icon, sort_order, Rebrickable part category ids, category the parts used to be in, description
PART_CATEGORIES = [
    ("skosy", "Скоси", "slope", 3, [3], "tsehlynky",
     "Скоси 18°–75°, подвійні та обернені — для дахів, капотів і крил."),
    ("arky-ta-vyhnuti-tsehlynky", "Арки та вигнуті цеглинки", "arch", 6, [37], "tsehlynky",
     "Арки, вигнуті скоси та цеглинки з плавними формами."),
    ("bazovi-plastyny", "Базові пластини", "baseplate", 15, [1], None,
     "Великі базові пластини — основа для міст, будинків і діорам."),
    ("paneli", "Панелі", "panel", 25, [23], "inshi-elementy", "Панелі-стінки, кутові та вигнуті панелі."),
    ("dlia-transportu", "Деталі для транспорту", "vehicle", 35, [36], "inshi-elementy",
     "Рами, кузови, бампери, щитки коліс та інші деталі для машин і поїздів."),
    ("sharniry-ta-povorotni-platformy", "Шарніри та поворотні платформи", "hinge", 55, [18], "inshi-elementy",
     "Шарніри, маніпулятори та поворотні платформи для рухомих конструкцій."),
    ("elektronika", "Електроніка та двигуни", "electronics", 75, [45], "elementy-technic",
     "Двигуни, хаби, батарейні блоки, датчики, світло та кабелі Powered Up, Power Functions і Mindstorms."),
    ("chastyny-minifihurok", "Частини мініфігурок", "minifig", 97, [59, 60, 61, 13], "aksesuary-dlia-fihurok",
     "Голови, торси та ноги — для збирання власних мініфігурок і ремонту."),
    ("volossia-ta-holovni-ubory", "Волосся та головні убори", "hair", 98, [65, 72], "aksesuary-dlia-fihurok",
     "Зачіски, шоломи, капелюхи, кепки та прикраси до них."),
    ("zbroia-ta-instrumenty", "Зброя та інструменти", "weapon", 101, [73], "aksesuary-dlia-fihurok",
     "Мечі, бластери, щити, чарівні палички та інструменти для мініфігурок."),
    ("ohorozhi-drabyny-ta-opory", "Огорожі, драбини та опори", "fence", 102, [32, 34], "inshi-elementy",
     "Огорожі, перила, драбини, стрижні, опори та стріли кранів."),
    ("kontejnery-ta-yashchyky", "Контейнери та ящики", "container", 103, [7], "inshi-elementy",
     "Скрині, ящики, бочки, шафи та інші ємності."),
    ("trubky-shlanhy-ta-nytky", "Трубки, шланги та нитки", "hose", 104, [30, 31], "inshi-elementy",
     "Гнучкі трубки, шланги, нитки, гумки та котушки."),
    ("prapory-ta-znaky", "Прапори та знаки", "flag", 105, [38], "inshi-elementy",
     "Прапори, банери, дорожні знаки та вивіски."),
    ("nalipky", "Наліпки", "sticker", 106, [58], None, "Оригінальні аркуші наліпок до наборів LEGO."),
    ("duplo", "Деталі DUPLO", "duplo", 107, [4], None,
     "Великі цеглинки та елементи DUPLO для наймолодших будівельників."),
]

# slug, name, icon, description — subcategories of «Аксесуари»
ACCESSORY_CATEGORIES = [
    ("zberihannia", "Зберігання та органайзери", "storage",
     "Контейнери-цеглинки, коробки, ланчбокси та органайзери для деталей."),
    ("vitryny-ta-pidstavky", "Вітрини та підставки", "display", "Вітрини, рамки й підставки для наборів і мініфігурок."),
    ("osvitlennia", "Освітлення", "light", "LED-підсвітка для наборів, ліхтарики та нічники."),
    ("separatory-ta-instrumenty", "Сепаратори та інструменти", "tool",
     "Сепаратори деталей, сортувальники та інші інструменти для збирання."),
    ("kantseliariia", "Канцелярія", "pencil", "Ручки, олівці, блокноти, щоденники та пенали."),
    ("sumky-ta-riukzaky", "Сумки та рюкзаки", "bag", "Рюкзаки, сумки й гаманці з героями LEGO."),
    ("odiah", "Одяг", "shirt", "Футболки, кепки, шкарпетки та інший одяг LEGO."),
    ("hodynnyky", "Годинники", "clock", "Наручні годинники та будильники."),
    ("mahnity", "Магніти", "magnet", "Магніти з мініфігурками та цеглинками."),
    ("ihry-ta-pazly", "Ігри та пазли", "puzzle", "Настільні ігри, пазли та відеоігри LEGO."),
    ("dekor-i-suveniry", "Декор і сувеніри", "gift",
     "М'які іграшки, світильники, кухлі, постери та подарунки для фанатів LEGO."),
    ("inshi-aksesuary", "Інші аксесуари", "star", "Аксесуари, що не ввійшли до інших розділів."),
]

# slug: (field, original text, new text) — applied only while the original text is still there
RENAMES = {
    "aksesuary-dlia-fihurok": [
        ("name", "Аксесуари", "Аксесуари для фігурок"),
        ("description", "Зброя, інструменти, посуд і головні убори для фігурок.",
         "Посуд, їжа, накидки, обладунки та інші дрібниці для мініфігурок."),
    ],
    "tsehlynky": [("description", "Класичні цеглинки, скоси, круглі та модифіковані елементи.",
                   "Класичні, круглі, клиноподібні та модифіковані цеглинки.")],
    "inshi-elementy": [("description", "Шарніри, панелі, стрижні, огорожі та спеціальні деталі.",
                        "Каміння, магніти, снаряди, енергетичні ефекти та інші спеціальні деталі.")],
    "aksesuary": [("description", "Брелоки, контейнери для зберігання та інші аксесуари LEGO.",
                   "Зберігання, вітрини, підсвітка, канцелярія та інші аксесуари LEGO.")],
}


def _ids(value: str) -> list[int]:
    return [int(x) for x in (value or "").split(",") if x.strip().isdigit()]


def _join(ids) -> str:
    return ",".join(str(i) for i in ids)


def _rename(Category, forward: bool):
    for slug, changes in RENAMES.items():
        cat = Category.objects.filter(slug=slug).first()
        if cat is None:
            continue
        for field, old, new in changes:
            src, dst = (old, new) if forward else (new, old)
            if getattr(cat, field) == src:
                setattr(cat, field, dst)
        cat.save()


def add_categories(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Part = apps.get_model("catalog", "Part")
    detali = Category.objects.filter(slug="detali", parent__isnull=True).first()
    if detali is not None:
        for slug, name, icon, order, rb, source_slug, desc in PART_CATEGORIES:
            cat = Category.objects.filter(slug=slug).first()
            if cat is None:
                cat = Category.objects.create(
                    slug=slug, name=name, kind="part", icon=icon, sort_order=order, is_active=True, parent=detali,
                    description=desc, rebrickable_part_categories=_join(rb))
            parts = Part.objects.filter(part_category_id__in=rb)
            parts.filter(category__isnull=True).update(category=cat)
            source = Category.objects.filter(slug=source_slug).first() if source_slug else None
            if source is not None:
                parts.filter(category=source).update(category=cat)
        # each Rebrickable id is auto-assigned by one category only, so the ids moved above leave their old
        # categories (older installs also kept the animals ids in «Інші елементи»)
        existing = set(Category.objects.values_list("slug", flat=True))
        owner = {rid: slug for slug, _n, _i, _o, rb, _s, _d in PART_CATEGORIES for rid in rb if slug in existing}
        if "tvaryny" in existing:
            owner.update({rid: "tvaryny" for rid in (28, 74, 75)})
        for cat in Category.objects.exclude(rebrickable_part_categories=""):
            ids = _ids(cat.rebrickable_part_categories)
            left = [i for i in ids if owner.get(i, cat.slug) == cat.slug]
            if left != ids:
                cat.rebrickable_part_categories = _join(left)
                cat.save(update_fields=["rebrickable_part_categories"])
    aksesuary = Category.objects.filter(slug="aksesuary", parent__isnull=True).first()
    if aksesuary is not None:
        for order, (slug, name, icon, desc) in enumerate(ACCESSORY_CATEGORIES):
            if not Category.objects.filter(slug=slug).exists():
                Category.objects.create(slug=slug, name=name, kind="accessory", icon=icon, sort_order=order * 10,
                                        is_active=True, parent=aksesuary, description=desc)
    _rename(Category, forward=True)


def remove_categories(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Part = apps.get_model("catalog", "Part")
    _rename(Category, forward=False)
    for slug, _name, _icon, _order, rb, source_slug, _desc in reversed(PART_CATEGORIES):
        cat = Category.objects.filter(slug=slug).first()
        if cat is None:
            continue
        source = Category.objects.filter(slug=source_slug).first() if source_slug else None
        Part.objects.filter(category=cat).update(category=source)
        if source is not None:
            ids = _ids(source.rebrickable_part_categories)
            source.rebrickable_part_categories = _join(ids + [i for i in rb if i not in ids])
            source.save(update_fields=["rebrickable_part_categories"])
        if not cat.products.exists():
            cat.delete()
    for slug, *_rest in ACCESSORY_CATEGORIES:
        cat = Category.objects.filter(slug=slug).first()
        if cat is not None and not cat.products.exists():
            cat.delete()


class Migration(migrations.Migration):
    dependencies = [("catalog", "0005_animals_category")]

    operations = [migrations.RunPython(add_categories, remove_categories)]
