"""Third level of part categories (heads, torsos, legs, hair, helmets, Technic beams, axles ...) and two new
part categories (minidoll parts, Bionicle and large figures).

Only categories are added, and reference catalogue parts (the LEGO parts directory, not shop listings) are
re-linked to the new subcategories when they still sit in the parent category or have none. Shop products are
not touched: every listing keeps the category it has.

On an empty database (fresh install) this does nothing — ``setup_store`` creates the full structure.
"""
from django.db import migrations
from django.db.models import Q

# slug, name, icon, sort_order, description, Rebrickable ids — new subcategories of «Деталі LEGO»
NEW_PART_CATEGORIES = [
    ('chastyny-minilialok', 'Частини мініляльок', 'minidoll', 99, 'Голови, торси та ноги мініляльок LEGO Friends, Disney та інших серій.', ''),
    ('bionicle', 'Bionicle та великі фігури', 'bionicle', 108, 'Деталі збірних фігур Bionicle, Hero Factory, Star Wars та інших великих фігур.', '41'),
]

# parent slug: [(slug, name, icon, description, Rebrickable ids, name prefixes)]
SUBCATEGORIES = {
    'tsehlynky': [
        ('zvychaini-tsehlynky', 'Звичайні цеглинки', 'brick', 'Класичні прямокутні цеглинки від 1 × 1 до 2 × 16.', '11', ()),
        ('modyfikovani-tsehlynky', 'Модифіковані цеглинки', 'brick', 'Цеглинки з шипами збоку, отворами, вирізами, фарами, кліпсами та іншими елементами.', '5', ()),
        ('kruhli-tsehlynky-ta-konusy', 'Круглі цеглинки та конуси', 'round', 'Круглі цеглинки, циліндри, конуси та куполи.', '20', ()),
        ('klynopodibni-tsehlynky', 'Клиноподібні цеглинки', 'wedge', 'Цеглинки-клини для носів кораблів і літаків.', '6', ()),
    ],
    'plastyny': [
        ('zvychaini-plastyny', 'Звичайні пластини', 'plate', 'Прямокутні пластини будь-якого розміру.', '14', ()),
        ('modyfikovani-plastyny', 'Модифіковані пластини', 'plate', 'Пластини з кронштейнами, кліпсами, ручками, рейками, шипами збоку та отворами.', '9', ()),
        ('kruhli-plastyny-ta-tarilky', 'Круглі пластини та тарілки', 'round', 'Круглі й вигнуті пластини, тарілки та антени-«тарілки».', '21', ()),
    ],
    'plytky': [
        ('zvychaini-plytky', 'Звичайні плитки', 'tile', 'Гладкі прямокутні плитки.', '19', ()),
        ('modyfikovani-plytky', 'Модифіковані плитки', 'tile', 'Плитки з решітками, кліпсами, ручками, рейками та іншими елементами.', '15', ()),
        ('kruhli-ta-vyhnuti-plytky', 'Круглі та вигнуті плитки', 'round', 'Круглі, вигнуті та чвертькруглі плитки.', '67', ()),
    ],
    'vikna-ta-dveri': [
        ('ramy-vikna-ta-dveri', 'Рами, вікна та двері', 'window', 'Віконні рами, скло, віконниці, двері та ворота.', '16', ()),
        ('lobove-sklo-ta-fiuzeliazh', 'Лобове скло та фюзеляж', 'windscreen', 'Лобове скло, кабіни та скляні частини фюзеляжу.', '47', ()),
    ],
    'kryla': [
        ('klynopodibni-plastyny', 'Клиноподібні пластини', 'wing', 'Крила-пластини лівого й правого боку.', '49', ()),
        ('korpusy-chovniv-i-litakiv', 'Корпуси човнів і літаків', 'boat', 'Корпуси та палуби човнів, частини літаків, хвости й пропелери.', '35', ()),
    ],
    'elementy-technic': [
        ('balky-technic', 'Балки', 'beam', 'Прямі, кутові та спеціальні балки Technic.', '51,55', ()),
        ('osi-technic', 'Осі', 'axle', 'Осі Technic будь-якої довжини, зі стопорами та без.', '46', ()),
        ('shtyfty-technic', 'Штифти', 'pin', 'Штифти Technic з тертям і без, з віссю, довгі та напівштифти.', '53', ()),
        ('vtulky-technic', 'Втулки', 'bush', 'Втулки та напіввтулки для осей Technic.', '54', ()),
        ('zjednuvachi-technic', "З'єднувачі", 'connector', "Кутові, поперечні та інші з'єднувачі осей і штифтів.", '12', ()),
        ('tsehlynky-technic', 'Цеглинки Technic', 'brick', 'Цеглинки з отворами для штифтів та осей.', '8', ()),
        ('paneli-technic', 'Панелі Technic', 'panel', 'Панелі та обтічники кузовів Technic.', '40', ()),
        ('kermo-pidviska-ta-dvyhun', 'Кермо, підвіска та двигун', 'steering', 'Кермові механізми, амортизатори, циліндри та поршні двигунів.', '25', ()),
        ('pnevmatyka', 'Пневматика', 'pneumatic', 'Пневмоциліндри, насоси, клапани та трубки.', '22', ()),
        ('mekhanika', 'Механіка', 'mechanic', 'Рейки, редуктори, диференціали та інші механізми.', '44', ()),
        ('spetsialni-elementy-technic', 'Спеціальні елементи Technic', 'technic', 'Рами, гусениці, ланцюги та інші особливі елементи Technic.', '26', ()),
    ],
    'tvaryny': [
        ('tvaryny-ta-istoty', 'Тварини та істоти', 'animal', 'Цілі фігурки тварин, птахів, риб і фантастичних істот.', '28', ()),
        ('chastyny-tila-tvaryn', 'Частини тіла тварин', 'animal', 'Голови, тулуби, хвости, крила та лапи тварин.', '75', ()),
        ('aksesuary-dlia-tvaryn', 'Аксесуари для тварин', 'animal', 'Сідла, упряж, нашийники та інші аксесуари.', '74', ()),
    ],
    'chastyny-minifihurok': [
        ('holovy', 'Голови', 'head', 'Голови мініфігурок з різними обличчями та виразами.', '59', ()),
        ('torsy', 'Торси', 'torso', 'Торси з руками та кистями, з принтами та без.', '60', ()),
        ('nohy', 'Ноги', 'legs', 'Ноги, стегна, короткі ніжки та спідниці-ноги.', '61', ()),
        ('inshi-chastyny-ta-mikrofihurky', 'Інші частини та мікрофігурки', 'minifig', 'Мікрофігурки, тіла дитячих фігурок, роботів і дроїдів.', '13', ()),
    ],
    'volossia-ta-holovni-ubory': [
        ('volossia', 'Волосся', 'hair', 'Зачіски для мініфігурок: короткі, довгі, хвости та коси.', '65', ('Hair',)),
        ('sholomy', 'Шоломи', 'helmet', 'Шоломи лицарів, пілотів, космонавтів, пожежників і поліції.', '65', ('Helmet',)),
        ('kapeliukhy-ta-masky', 'Капелюхи, маски та інші головні убори', 'hat', 'Капелюхи, кепки, шапки, капюшони, маски та костюми-головні убори.', '65', ()),
        ('prykrasy-do-holovnykh-uboriv', 'Прикраси до головних уборів', 'hair', "Візори, плюмажі, пір'я та інші прикраси для шоломів і капелюхів.", '72', ()),
    ],
    'chastyny-minilialok': [
        ('holovy-minilialok', 'Голови мініляльок', 'minidoll', 'Голови мініляльок, часто з волоссям.', '62', ()),
        ('torsy-minilialok', 'Торси мініляльок', 'minidoll', 'Торси мініляльок з руками.', '63', ()),
        ('nohy-minilialok', 'Ноги мініляльок', 'minidoll', 'Ноги, спідниці та штани мініляльок.', '64', ()),
    ],
    'aksesuary-dlia-fihurok': [
        ('predmety-ta-obladnannia', 'Предмети та обладнання', 'cup', 'Посуд, їжа, книги, спорядження, спортивний інвентар, музичні інструменти та інші предмети.', '27', ()),
        ('nakydky-ta-obladunky', 'Накидки, обладунки та шарфи', 'cape', 'Плащі, накидки, обладунки, жилети, шарфи та інші речі на шию.', '71', ()),
        ('spidnytsi-ta-poiasy', 'Спідниці та пояси', 'skirt', 'Спідниці, пояси, сумки на пояс та інші речі на стегна.', '70', ()),
    ],
    'zbroia-ta-instrumenty': [
        ('zbroia', 'Зброя', 'sword', 'Мечі, списи, луки, бластери та інша зброя мініфігурок.', '73', ()),
        ('shchyty', 'Щити', 'shield', 'Круглі, трикутні та фантазійні щити.', '73', ('Shield',)),
        ('instrumenty', 'Інструменти', 'tool', 'Ключі, молотки, пилки, лопати та інші інструменти.', '73', ('Tool',)),
    ],
    'ohorozhi-drabyny-ta-opory': [
        ('ohorozhi-ta-drabyny', 'Огорожі, драбини та стрижні', 'fence', 'Огорожі, перила, драбини, решітки та стрижні.', '32', ()),
        ('opory-balky-ta-krany', 'Опори, балки та крани', 'support', 'Опори, балки-ферми, стріли та гаки кранів.', '34', ()),
    ],
    'trubky-shlanhy-ta-nytky': [
        ('trubky-ta-shlanhy', 'Трубки та шланги', 'hose', 'Гнучкі й жорсткі трубки та шланги.', '30', ()),
        ('nytky-humky-ta-kotushky', 'Нитки, гумки та котушки', 'hose', 'Нитки, ланцюжки, гумки та котушки.', '31', ()),
    ],
    'inshi-elementy': [
        ('kaminnia-ta-skeli', 'Каміння та скелі', 'rock', 'Каміння, скелі та уламки породи.', '33', ()),
        ('mahnity-ta-trymachi', 'Магніти та тримачі', 'magnet', 'Магніти й тримачі для них.', '39', ()),
        ('snariady-ta-puskovi-mekhanizmy', 'Снаряди та пускові механізми', 'launcher', 'Снаряди, ракети, диски та пускові механізми.', '68', ()),
        ('enerhetychni-efekty', 'Енергетичні ефекти', 'effect', "Полум'я, вибухи, хвилі, блискавки та інші ефекти.", '69', ()),
        ('inshi-spetsialni-detali', 'Інші спеціальні деталі', 'other', 'Деталі, що не ввійшли до інших розділів.', '24', ()),
    ],
}


def _ids(value):
    return [int(x) for x in (value or "").split(",") if x.strip().isdigit()]


def _join(ids):
    return ",".join(str(i) for i in ids)


def _starts(prefixes):
    q = Q()
    for prefix in prefixes:
        q |= Q(name__istartswith=prefix)
    return q


def add_subcategories(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Part = apps.get_model("catalog", "Part")
    detali = Category.objects.filter(slug="detali", parent__isnull=True).first()
    if detali is None:
        return
    for slug, name, icon, order, desc, rb in NEW_PART_CATEGORIES:
        cat = Category.objects.filter(slug=slug).first()
        if cat is None:
            cat = Category.objects.create(slug=slug, name=name, kind="part", icon=icon, sort_order=order,
                                          is_active=True, parent=detali, description=desc,
                                          rebrickable_part_categories=rb)
        if rb:
            Part.objects.filter(part_category_id__in=_ids(rb), category__isnull=True).update(category=cat)
    for parent_slug, children in SUBCATEGORIES.items():
        parent = Category.objects.filter(slug=parent_slug).first()
        if parent is None:
            continue
        created = {}
        for order, (slug, name, icon, desc, rb, prefixes) in enumerate(children):
            cat = Category.objects.filter(slug=slug).first()
            if cat is None:
                cat = Category.objects.create(slug=slug, name=name, kind="part", icon=icon, sort_order=order * 10,
                                              is_active=True, parent=parent, description=desc,
                                              rebrickable_part_categories="" if prefixes else rb)
            created[slug] = cat
        # parts named «Hair…», «Helmet…», «Shield…» first, then the rest of the same part types
        for slug, _name, _icon, _desc, rb, prefixes in sorted(children, key=lambda row: not row[5]):
            parts = Part.objects.filter(Q(category=parent) | Q(category__isnull=True), part_category_id__in=_ids(rb))
            if prefixes:
                parts = parts.filter(_starts(prefixes))
            parts.update(category=created[slug])
    # each Rebrickable id is auto-assigned by one category only: the subcategories now own them
    existing = set(Category.objects.values_list("slug", flat=True))
    owner = {}
    for children in SUBCATEGORIES.values():
        for slug, _name, _icon, _desc, rb, prefixes in children:
            if slug in existing and not prefixes:
                owner.update({rid: slug for rid in _ids(rb)})
    for cat in Category.objects.exclude(rebrickable_part_categories=""):
        ids = _ids(cat.rebrickable_part_categories)
        left = [i for i in ids if owner.get(i, cat.slug) == cat.slug]
        if left != ids:
            cat.rebrickable_part_categories = _join(left)
            cat.save(update_fields=["rebrickable_part_categories"])


def remove_subcategories(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Part = apps.get_model("catalog", "Part")
    for parent_slug, children in SUBCATEGORIES.items():
        parent = Category.objects.filter(slug=parent_slug).first()
        ids = []
        for slug, _name, _icon, _desc, rb, _prefixes in children:
            ids += [i for i in _ids(rb) if i not in ids]
            cat = Category.objects.filter(slug=slug).first()
            if cat is None:
                continue
            Part.objects.filter(category=cat).update(category=parent)
            if not cat.products.exists():
                cat.delete()
        if parent is not None and not parent.rebrickable_part_categories:
            parent.rebrickable_part_categories = _join(ids)
            parent.save(update_fields=["rebrickable_part_categories"])
    for slug, *_rest in NEW_PART_CATEGORIES:
        cat = Category.objects.filter(slug=slug).first()
        if cat is not None:
            Part.objects.filter(category=cat).update(category=None)
            if not cat.products.exists() and not cat.children.exists():
                cat.delete()


class Migration(migrations.Migration):
    dependencies = [("catalog", "0006_more_categories")]

    operations = [migrations.RunPython(add_subcategories, remove_subcategories)]
