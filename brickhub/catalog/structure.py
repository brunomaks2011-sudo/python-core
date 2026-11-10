"""Shop structure: navigation categories, LEGO series settings, colour names.

``apply_structure()`` is idempotent – it is safe to run on every deploy.
"""
from __future__ import annotations

from django.core.cache import cache
from django.db import transaction

from .models import Category, Color, Theme

# slug, name, icon, description, Rebrickable part category ids (subcategories of «Деталі LEGO»)
PART_CATEGORIES = [
    ("tsehlynky", "Цеглинки", "brick", "Класичні, круглі, клиноподібні та модифіковані цеглинки.", ""),
    ("skosy", "Скоси", "slope", "Скоси 18°–75°, подвійні та обернені — для дахів, капотів і крил.", "3"),
    ("arky-ta-vyhnuti-tsehlynky", "Арки та вигнуті цеглинки", "arch",
     "Арки, вигнуті скоси та цеглинки з плавними формами.", "37"),
    ("plastyny", "Пластини", "plate", "Пластини, кронштейни та круглі пластини для будь-яких конструкцій.", ""),
    ("bazovi-plastyny", "Базові пластини", "baseplate", "Великі базові пластини — основа для міст, будинків і діорам.",
     "1"),
    ("plytky", "Плитки", "tile", "Гладкі плитки без шипів — для фінішного вигляду моделей.", ""),
    ("paneli", "Панелі", "panel", "Панелі-стінки, кутові та вигнуті панелі.", "23"),
    ("kolesa-ta-shyny", "Колеса та шини", "wheel", "Колеса, диски та шини для машин і техніки.", "29"),
    ("dlia-transportu", "Деталі для транспорту", "vehicle",
     "Рами, кузови, бампери, щитки коліс та інші деталі для машин і поїздів.", "36"),
    ("vikna-ta-dveri", "Вікна та двері", "window", "Рами, скло, двері та лобове скло.", ""),
    ("kryla", "Крила", "wing", "Крила-пластини та клиноподібні пластини для літаків і кораблів.", ""),
    ("sharniry-ta-povorotni-platformy", "Шарніри та поворотні платформи", "hinge",
     "Шарніри, маніпулятори та поворотні платформи для рухомих конструкцій.", "18"),
    ("shesterni", "Шестерні", "gear", "Шестерні Technic, зубчасті рейки та передачі.", "52"),
    ("elementy-technic", "Елементи Technic", "technic", "Балки, осі, штифти, втулки та з'єднувачі Technic.",
     ""),
    ("elektronika", "Електроніка та двигуни", "electronics",
     "Двигуни, хаби, батарейні блоки, датчики, світло та кабелі Powered Up, Power Functions і Mindstorms.", "45"),
    ("prozori-detali", "Прозорі деталі", "trans", "Усі деталі прозорих кольорів: скло, вогні, кристали.", ""),
    ("roslyny", "Рослини", "plant", "Квіти, листя, дерева та інша зелень.", "76"),
    ("tvaryny", "Тварини", "animal", "Тварини, птахи, риби та фантастичні істоти, їхні частини тіла й аксесуари.",
     ""),
    ("chastyny-minifihurok", "Частини мініфігурок", "minifig",
     "Голови, торси та ноги — для збирання власних мініфігурок і ремонту.", ""),
    ("volossia-ta-holovni-ubory", "Волосся та головні убори", "hair",
     "Зачіски, шоломи, капелюхи, кепки та прикраси до них.", ""),
    ("chastyny-minilialok", "Частини мініляльок", "minidoll",
     "Голови, торси та ноги мініляльок LEGO Friends, Disney та інших серій.", ""),
    ("aksesuary-dlia-fihurok", "Аксесуари для фігурок", "accessory",
     "Посуд, їжа, накидки, обладунки та інші дрібниці для мініфігурок.", ""),
    ("zbroia-ta-instrumenty", "Зброя та інструменти", "weapon",
     "Мечі, бластери, щити, чарівні палички та інструменти для мініфігурок.", ""),
    ("ohorozhi-drabyny-ta-opory", "Огорожі, драбини та опори", "fence",
     "Огорожі, перила, драбини, стрижні, опори та стріли кранів.", ""),
    ("kontejnery-ta-yashchyky", "Контейнери та ящики", "container", "Скрині, ящики, бочки, шафи та інші ємності.", "7"),
    ("trubky-shlanhy-ta-nytky", "Трубки, шланги та нитки", "hose", "Гнучкі трубки, шланги, нитки, гумки та котушки.",
     ""),
    ("prapory-ta-znaky", "Прапори та знаки", "flag", "Прапори, банери, дорожні знаки та вивіски.", "38"),
    ("nalipky", "Наліпки", "sticker", "Оригінальні аркуші наліпок до наборів LEGO.", "58"),
    ("duplo", "Деталі DUPLO", "duplo", "Великі цеглинки та елементи DUPLO для наймолодших будівельників.", "4"),
    ("bionicle", "Bionicle та великі фігури", "bionicle",
     "Деталі збірних фігур Bionicle, Hero Factory, Star Wars та інших великих фігур.", "41"),
    ("inshi-elementy", "Інші елементи", "other",
     "Каміння, магніти, снаряди, енергетичні ефекти та інші спеціальні деталі.", ""),
]

# The third level follows the official part types (Rebrickable part categories).
# parent slug: [(slug, name, icon, description, Rebrickable ids, name prefixes)]
# A subcategory with name prefixes gets the parts of its types whose official (English) name starts with one of
# them; the subcategory of the same types without prefixes gets the rest.
PART_SUBCATEGORIES = {
    "tsehlynky": [
        ("zvychaini-tsehlynky", "Звичайні цеглинки", "brick", "Класичні прямокутні цеглинки від 1 × 1 до 2 × 16.",
         "11", ()),
        ("modyfikovani-tsehlynky", "Модифіковані цеглинки", "brick",
         "Цеглинки з шипами збоку, отворами, вирізами, фарами, кліпсами та іншими елементами.", "5", ()),
        ("kruhli-tsehlynky-ta-konusy", "Круглі цеглинки та конуси", "round",
         "Круглі цеглинки, циліндри, конуси та куполи.", "20", ()),
        ("klynopodibni-tsehlynky", "Клиноподібні цеглинки", "wedge", "Цеглинки-клини для носів кораблів і літаків.",
         "6", ()),
    ],
    "plastyny": [
        ("zvychaini-plastyny", "Звичайні пластини", "plate", "Прямокутні пластини будь-якого розміру.", "14", ()),
        ("modyfikovani-plastyny", "Модифіковані пластини", "plate",
         "Пластини з кронштейнами, кліпсами, ручками, рейками, шипами збоку та отворами.", "9", ()),
        ("kruhli-plastyny-ta-tarilky", "Круглі пластини та тарілки", "round",
         "Круглі й вигнуті пластини, тарілки та антени-«тарілки».", "21", ()),
    ],
    "plytky": [
        ("zvychaini-plytky", "Звичайні плитки", "tile", "Гладкі прямокутні плитки.", "19", ()),
        ("modyfikovani-plytky", "Модифіковані плитки", "tile",
         "Плитки з решітками, кліпсами, ручками, рейками та іншими елементами.", "15", ()),
        ("kruhli-ta-vyhnuti-plytky", "Круглі та вигнуті плитки", "round",
         "Круглі, вигнуті та чвертькруглі плитки.", "67", ()),
    ],
    "vikna-ta-dveri": [
        ("ramy-vikna-ta-dveri", "Рами, вікна та двері", "window", "Віконні рами, скло, віконниці, двері та ворота.",
         "16", ()),
        ("lobove-sklo-ta-fiuzeliazh", "Лобове скло та фюзеляж", "windscreen",
         "Лобове скло, кабіни та скляні частини фюзеляжу.", "47", ()),
    ],
    "kryla": [
        ("klynopodibni-plastyny", "Клиноподібні пластини", "wing", "Крила-пластини лівого й правого боку.", "49", ()),
        ("korpusy-chovniv-i-litakiv", "Корпуси човнів і літаків", "boat",
         "Корпуси та палуби човнів, частини літаків, хвости й пропелери.", "35", ()),
    ],
    "elementy-technic": [
        ("balky-technic", "Балки", "beam", "Прямі, кутові та спеціальні балки Technic.", "51,55", ()),
        ("osi-technic", "Осі", "axle", "Осі Technic будь-якої довжини, зі стопорами та без.", "46", ()),
        ("shtyfty-technic", "Штифти", "pin", "Штифти Technic з тертям і без, з віссю, довгі та напівштифти.", "53", ()),
        ("vtulky-technic", "Втулки", "bush", "Втулки та напіввтулки для осей Technic.", "54", ()),
        ("zjednuvachi-technic", "З'єднувачі", "connector", "Кутові, поперечні та інші з'єднувачі осей і штифтів.",
         "12", ()),
        ("tsehlynky-technic", "Цеглинки Technic", "brick", "Цеглинки з отворами для штифтів та осей.", "8", ()),
        ("paneli-technic", "Панелі Technic", "panel", "Панелі та обтічники кузовів Technic.", "40", ()),
        ("kermo-pidviska-ta-dvyhun", "Кермо, підвіска та двигун", "steering",
         "Кермові механізми, амортизатори, циліндри та поршні двигунів.", "25", ()),
        ("pnevmatyka", "Пневматика", "pneumatic", "Пневмоциліндри, насоси, клапани та трубки.", "22", ()),
        ("mekhanika", "Механіка", "mechanic", "Рейки, редуктори, диференціали та інші механізми.", "44", ()),
        ("spetsialni-elementy-technic", "Спеціальні елементи Technic", "technic",
         "Рами, гусениці, ланцюги та інші особливі елементи Technic.", "26", ()),
    ],
    "tvaryny": [
        ("tvaryny-ta-istoty", "Тварини та істоти", "animal", "Цілі фігурки тварин, птахів, риб і фантастичних істот.",
         "28", ()),
        ("chastyny-tila-tvaryn", "Частини тіла тварин", "animal", "Голови, тулуби, хвости, крила та лапи тварин.", "75",
         ()),
        ("aksesuary-dlia-tvaryn", "Аксесуари для тварин", "animal", "Сідла, упряж, нашийники та інші аксесуари.", "74",
         ()),
    ],
    "chastyny-minifihurok": [
        ("holovy", "Голови", "head", "Голови мініфігурок з різними обличчями та виразами.", "59", ()),
        ("torsy", "Торси", "torso", "Торси з руками та кистями, з принтами та без.", "60", ()),
        ("nohy", "Ноги", "legs", "Ноги, стегна, короткі ніжки та спідниці-ноги.", "61", ()),
        ("inshi-chastyny-ta-mikrofihurky", "Інші частини та мікрофігурки", "minifig",
         "Мікрофігурки, тіла дитячих фігурок, роботів і дроїдів.", "13", ()),
    ],
    "volossia-ta-holovni-ubory": [
        ("volossia", "Волосся", "hair", "Зачіски для мініфігурок: короткі, довгі, хвости та коси.", "65", ("Hair",)),
        ("sholomy", "Шоломи", "helmet", "Шоломи лицарів, пілотів, космонавтів, пожежників і поліції.", "65",
         ("Helmet",)),
        ("kapeliukhy-ta-masky", "Капелюхи, маски та інші головні убори", "hat",
         "Капелюхи, кепки, шапки, капюшони, маски та костюми-головні убори.", "65", ()),
        ("prykrasy-do-holovnykh-uboriv", "Прикраси до головних уборів", "hair",
         "Візори, плюмажі, пір'я та інші прикраси для шоломів і капелюхів.", "72", ()),
    ],
    "chastyny-minilialok": [
        ("holovy-minilialok", "Голови мініляльок", "minidoll", "Голови мініляльок, часто з волоссям.", "62", ()),
        ("torsy-minilialok", "Торси мініляльок", "minidoll", "Торси мініляльок з руками.", "63", ()),
        ("nohy-minilialok", "Ноги мініляльок", "minidoll", "Ноги, спідниці та штани мініляльок.", "64", ()),
    ],
    "aksesuary-dlia-fihurok": [
        ("predmety-ta-obladnannia", "Предмети та обладнання", "cup",
         "Посуд, їжа, книги, спорядження, спортивний інвентар, музичні інструменти та інші предмети.", "27", ()),
        ("nakydky-ta-obladunky", "Накидки, обладунки та шарфи", "cape",
         "Плащі, накидки, обладунки, жилети, шарфи та інші речі на шию.", "71", ()),
        ("spidnytsi-ta-poiasy", "Спідниці та пояси", "skirt", "Спідниці, пояси, сумки на пояс та інші речі на стегна.",
         "70", ()),
    ],
    "zbroia-ta-instrumenty": [
        ("zbroia", "Зброя", "sword", "Мечі, списи, луки, бластери та інша зброя мініфігурок.", "73", ()),
        ("shchyty", "Щити", "shield", "Круглі, трикутні та фантазійні щити.", "73", ("Shield",)),
        ("instrumenty", "Інструменти", "tool", "Ключі, молотки, пилки, лопати та інші інструменти.", "73", ("Tool",)),
    ],
    "ohorozhi-drabyny-ta-opory": [
        ("ohorozhi-ta-drabyny", "Огорожі, драбини та стрижні", "fence", "Огорожі, перила, драбини, решітки та стрижні.",
         "32", ()),
        ("opory-balky-ta-krany", "Опори, балки та крани", "support", "Опори, балки-ферми, стріли та гаки кранів.", "34",
         ()),
    ],
    "trubky-shlanhy-ta-nytky": [
        ("trubky-ta-shlanhy", "Трубки та шланги", "hose", "Гнучкі й жорсткі трубки та шланги.", "30", ()),
        ("nytky-humky-ta-kotushky", "Нитки, гумки та котушки", "hose", "Нитки, ланцюжки, гумки та котушки.", "31", ()),
    ],
    "inshi-elementy": [
        ("kaminnia-ta-skeli", "Каміння та скелі", "rock", "Каміння, скелі та уламки породи.", "33", ()),
        ("mahnity-ta-trymachi", "Магніти та тримачі", "magnet", "Магніти й тримачі для них.", "39", ()),
        ("snariady-ta-puskovi-mekhanizmy", "Снаряди та пускові механізми", "launcher",
         "Снаряди, ракети, диски та пускові механізми.", "68", ()),
        ("enerhetychni-efekty", "Енергетичні ефекти", "effect", "Полум'я, вибухи, хвилі, блискавки та інші ефекти.",
         "69", ()),
        ("inshi-spetsialni-detali", "Інші спеціальні деталі", "other", "Деталі, що не ввійшли до інших розділів.", "24",
         ()),
    ],
}

# slug, name, icon, description (subcategories of «Аксесуари»)
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

ROOT_CATEGORIES = [
    ("nabory", "Набори LEGO", "set", "box", "Оригінальні набори LEGO усіх популярних серій."),
    ("detali", "Деталі LEGO", "part", "brick",
     "Окремі деталі LEGO за номером (Design ID) та кольором — будь-яка кількість."),
    ("minifihurky", "Мініфігурки", "minifig", "figure", "Мініфігурки LEGO за номером та серією."),
    ("breloky", "Брелоки", "keychain", "key", "Брелоки LEGO: мініфігурки, цеглинки та герої улюблених серій."),
    ("knyhy-z-fihurkamy", "Книги з фігурками", "book", "book", "Книги LEGO з ексклюзивною мініфігуркою в комплекті."),
    ("aksesuary", "Аксесуари", "accessory", "star",
     "Зберігання, вітрини, підсвітка, канцелярія та інші аксесуари LEGO."),
]

# slug, display title, Rebrickable theme ids, primary (sets menu), minifig menu, accent, description
SERIES = [
    ("city", "LEGO City", [52], True, True, "#0A63C9",
     "Місто, у якому завжди щось відбувається: поліція, пожежники, будівельники та космос."),
    ("technic", "LEGO Technic", [1], True, False, "#3B3F46",
     "Справжня механіка: передачі, підвіска та моделі суперкарів і спецтехніки."),
    ("star-wars", "LEGO Star Wars", [158], True, True, "#1B1B1F",
     "Кораблі, бойові машини та герої далекої-далекої галактики."),
    ("icons", "LEGO Icons", [721, 155], True, False, "#111111",
     "Колекційні моделі для дорослих: автомобілі, будівлі та легендарні об'єкти."),
    ("creator", "LEGO Creator", [22], True, False, "#F28C28",
     "Набори 3-в-1: з одного комплекту — три різні моделі."),
    ("speed-champions", "LEGO Speed Champions", [601], True, False, "#D7261E",
     "Детальні копії легендарних гоночних і спортивних автомобілів."),
    ("harry-potter", "LEGO Harry Potter", [246], True, True, "#7A1F2B",
     "Гоґвортс, Діаґон-Алея та магічні пригоди."),
    ("ninjago", "LEGO NINJAGO", [435], True, True, "#C8102E",
     "Ніндзя, дракони та механічні роботи."),
    ("marvel", "LEGO Marvel", [696], True, True, "#B11313",
     "Месники, Людина-павук та інші супергерої Marvel."),
    ("minecraft", "LEGO Minecraft", [577], True, False, "#3C8527",
     "Світ кубиків, кріперів і пригод — тепер із цеглинок."),
    ("friends", "LEGO Friends", [494], True, False, "#C2187D",
     "Історії про дружбу, творчість і життя в Хартлейк-Сіті."),
    ("architecture", "LEGO Architecture", [252], True, False, "#5B6770",
     "Знамениті будівлі та міста світу в мініатюрі."),
    ("ideas", "LEGO Ideas", [576], True, False, "#F2B705",
     "Набори, придумані фанатами й обрані спільнотою."),
    ("super-mario", "LEGO Super Mario", [690], True, False, "#E52521",
     "Інтерактивні рівні з Маріо, Луїджі та друзями."),
    ("dc", "DC Super Heroes", [695], False, True, "#1A3A8F", "Бетмен, Супермен та герої всесвіту DC."),
    ("collectible-minifigures", "Collectible Minifigures", [535], False, True, "#6A2C91",
     "Колекційні мініфігурки серій CMF."),
    ("jurassic-world", "LEGO Jurassic World", [602], False, False, "#2E6B30", "Динозаври та їхні дослідники."),
    ("disney", "LEGO Disney", [608], False, False, "#2A5DAA", "Улюблені персонажі та замки Disney."),
    ("botanicals", "LEGO Botanicals", [769], False, False, "#4E8F3A", "Квіти й рослини, що не в'януть."),
    ("dreamzzz", "LEGO DREAMZzz", [749], False, False, "#5C3BA8", "Світ снів і фантазій."),
    ("lego-art", "LEGO Art", [709], False, False, "#2B2B2B", "Мозаїки та картини з деталей."),
]

COLOR_UK = {
    "Black": "Чорний", "White": "Білий", "Red": "Червоний", "Blue": "Синій", "Yellow": "Жовтий",
    "Green": "Зелений", "Light Bluish Gray": "Світло-сірий блакитнуватий", "Dark Bluish Gray": "Темно-сірий блакитнуватий",
    "Light Gray": "Світло-сірий (класичний)", "Dark Gray": "Темно-сірий (класичний)", "Reddish Brown": "Червоно-коричневий",
    "Brown": "Коричневий", "Dark Brown": "Темно-коричневий", "Tan": "Бежевий", "Dark Tan": "Темно-бежевий",
    "Orange": "Помаранчевий", "Dark Orange": "Темно-помаранчевий", "Bright Light Orange": "Яскраво-світло-помаранчевий",
    "Light Orange": "Світло-помаранчевий", "Lime": "Лаймовий", "Bright Green": "Яскраво-зелений",
    "Dark Green": "Темно-зелений", "Sand Green": "Пісочно-зелений", "Olive Green": "Оливковий",
    "Yellowish Green": "Жовтувато-зелений", "Medium Lime": "Середній лаймовий", "Dark Red": "Темно-червоний",
    "Dark Blue": "Темно-синій", "Medium Blue": "Середній синій", "Sand Blue": "Пісочно-синій",
    "Bright Light Blue": "Яскраво-блакитний", "Light Blue": "Блакитний", "Medium Azure": "Середній лазуровий",
    "Dark Azure": "Темно-лазуровий", "Dark Turquoise": "Темно-бірюзовий", "Light Aqua": "Світла аква",
    "Pink": "Рожевий", "Bright Pink": "Яскраво-рожевий", "Dark Pink": "Темно-рожевий", "Magenta": "Пурпуровий",
    "Coral": "Кораловий", "Purple": "Фіолетовий", "Dark Purple": "Темно-фіолетовий",
    "Medium Lavender": "Середній лавандовий", "Lavender": "Лавандовий", "Bright Light Yellow": "Яскраво-світло-жовтий",
    "Medium Nougat": "Середня нуга", "Nougat": "Нуга", "Light Nougat": "Світла нуга", "Dark Nougat": "Темна нуга",
    "Pearl Gold": "Перламутрове золото", "Flat Silver": "Матове срібло", "Metallic Silver": "Металік срібло",
    "Metallic Gold": "Металік золото", "Pearl Dark Gray": "Перламутровий темно-сірий", "Chrome Gold": "Хром золото",
    "Chrome Silver": "Хром срібло", "Trans-Clear": "Прозорий", "Trans-Black": "Прозорий чорний",
    "Trans-Brown": "Прозорий коричневий", "Trans-Red": "Прозорий червоний", "Trans-Light Blue": "Прозорий блакитний",
    "Trans-Dark Blue": "Прозорий темно-синій", "Trans-Medium Blue": "Прозорий середній синій",
    "Trans-Green": "Прозорий зелений", "Trans-Bright Green": "Прозорий яскраво-зелений",
    "Trans-Neon Green": "Прозорий неоново-зелений", "Trans-Yellow": "Прозорий жовтий",
    "Trans-Orange": "Прозорий помаранчевий", "Trans-Neon Orange": "Прозорий неоново-помаранчевий",
    "Trans-Purple": "Прозорий фіолетовий", "Trans-Pink": "Прозорий рожевий", "Trans-Dark Pink": "Прозорий темно-рожевий",
    "Glow In Dark Opaque": "Світиться в темряві", "Glow in Dark White": "Світиться в темряві (білий)",
    "Very Light Gray": "Дуже світло-сірий", "Very Light Bluish Gray": "Дуже світло-сірий блакитнуватий",
    "Reddish Orange": "Червоно-помаранчевий", "Neon Orange": "Неоново-помаранчевий", "Neon Green": "Неоново-зелений",
    "Light Pink": "Світло-рожевий", "Medium Dark Pink": "Середній темно-рожевий",
}


def _finish_for(name: str) -> str:
    low = name.lower()
    for prefix, finish in (("trans", "trans"), ("glitter", "glitter"), ("chrome", "chrome"), ("pearl", "pearl"),
                           ("metallic", "metallic"), ("glow", "glow"), ("opal", "satin"), ("satin", "satin"),
                           ("speckle", "speckle")):
        if low.startswith(prefix) or f" {prefix}" in low:
            return finish
    return "solid"


@transaction.atomic
def apply_structure() -> dict:
    """Create/refresh navigation categories, series flags and Ukrainian colour names."""
    stats = {"categories": 0, "series": 0, "colors": 0}
    for order, (slug, name, kind, icon, desc) in enumerate(ROOT_CATEGORIES):
        Category.objects.update_or_create(
            slug=slug, defaults={"name": name, "kind": kind, "icon": icon, "description": desc,
                                 "sort_order": order * 10, "parent": None})
        stats["categories"] += 1
    detali = Category.objects.get(slug="detali")
    for order, (slug, name, icon, desc, rb) in enumerate(PART_CATEGORIES):
        Category.objects.update_or_create(
            slug=slug, defaults={"name": name, "kind": "part", "icon": icon, "description": desc,
                                 "rebrickable_part_categories": rb, "sort_order": order * 10, "parent": detali})
        stats["categories"] += 1
    for parent_slug, children in PART_SUBCATEGORIES.items():
        parent = Category.objects.get(slug=parent_slug)
        for order, (slug, name, icon, desc, rb, prefixes) in enumerate(children):
            Category.objects.update_or_create(
                slug=slug, defaults={"name": name, "kind": "part", "icon": icon, "description": desc,
                                     "rebrickable_part_categories": "" if prefixes else rb,
                                     "sort_order": order * 10, "parent": parent})
            stats["categories"] += 1
    aksesuary = Category.objects.get(slug="aksesuary")
    for order, (slug, name, icon, desc) in enumerate(ACCESSORY_CATEGORIES):
        Category.objects.update_or_create(
            slug=slug, defaults={"name": name, "kind": "accessory", "icon": icon, "description": desc,
                                 "sort_order": order * 10, "parent": aksesuary})
        stats["categories"] += 1

    used_slugs = set()
    for order, (slug, title, rb_ids, primary, figs, accent, desc) in enumerate(SERIES):
        theme = Theme.objects.filter(rebrickable_id=rb_ids[0]).first()
        if theme is None:
            theme = Theme.objects.filter(slug=slug).first() or Theme(rebrickable_id=rb_ids[0], name=title)
        clash = Theme.objects.filter(slug=slug).exclude(pk=theme.pk).first()
        if clash:
            clash.slug = f"{clash.slug}-{clash.pk or 'x'}"
            clash.save(update_fields=["slug"])
        theme.slug = slug
        theme.title = title
        theme.is_primary = primary
        theme.show_in_minifigs = figs
        theme.accent = accent
        if not theme.description:
            theme.description = desc
        theme.sort_order = order * 10
        theme.parent = None
        theme.save()
        used_slugs.add(slug)
        # extra roots (e.g. Modular Buildings) are shown inside the main series
        for extra in rb_ids[1:]:
            Theme.objects.filter(rebrickable_id=extra).update(parent=theme)
        stats["series"] += 1

    for color in Color.objects.all():
        changed = False
        uk = COLOR_UK.get(color.name, "")
        if uk and not color.name_uk:
            color.name_uk = uk
            changed = True
        finish = _finish_for(color.name)
        if color.finish == "solid" and finish != "solid":
            color.finish = finish
            changed = True
        if changed:
            color.save()
            stats["colors"] += 1
    cache.delete("nav:v1")
    return stats


def subcategory_parents() -> dict[str, str]:
    """{third-level slug: its part category slug}"""
    return {child[0]: parent for parent, children in PART_SUBCATEGORIES.items() for child in children}


def name_rules() -> dict[int, list[tuple[tuple[str, ...], str]]]:
    """{Rebrickable part category id: [(lower-case name prefixes, shop category slug)]}"""
    rules: dict[int, list[tuple[tuple[str, ...], str]]] = {}
    for children in PART_SUBCATEGORIES.values():
        for slug, _name, _icon, _desc, rb, prefixes in children:
            if prefixes:
                for rid in (int(x) for x in rb.split(",") if x.strip().isdigit()):
                    rules.setdefault(rid, []).append((tuple(x.lower() for x in prefixes), slug))
    return rules


PART_CATEGORY_UK = {
    "Baseplates": "Базові пластини", "Bricks Sloped": "Скоси", "Duplo, Quatro and Primo": "Duplo, Quatro та Primo",
    "Bricks Special": "Цеглинки модифіковані", "Bricks Wedged": "Цеглинки клиноподібні", "Containers": "Контейнери",
    "Technic Bricks": "Цеглинки Technic", "Plates Special": "Пластини модифіковані", "Bricks": "Цеглинки",
    "Technic Connectors": "З'єднувачі Technic", "Minifigs": "Мініфігурки", "Plates": "Пластини",
    "Tiles Special": "Плитки модифіковані", "Windows and Doors": "Вікна та двері", "Gear Parts": "Аксесуари LEGO",
    "Hinges, Arms and Turntables": "Шарніри, важелі та поворотні платформи", "Tiles": "Плитки",
    "Bricks Round and Cones": "Круглі цеглинки та конуси",
    "Plates Round Curved and Dishes": "Круглі й вигнуті пластини, тарілки", "Pneumatics": "Пневматика",
    "Panels": "Панелі", "Other": "Інше", "Technic Steering, Suspension and Engine": "Technic: кермо, підвіска, двигун",
    "Technic Special": "Technic: спеціальні", "Minifig Accessories": "Аксесуари для мініфігурок",
    "Animals / Creatures": "Тварини та істоти", "Wheels and Tyres": "Колеса та шини",
    "Tubes and Hoses": "Трубки та шланги", "String, Bands and Reels": "Нитки, гумки та котушки",
    "Bars, Ladders and Fences": "Стрижні, драбини та огорожі", "Rock": "Скелі та каміння",
    "Supports, Girders and Cranes": "Опори, балки та крани", "Transportation - Sea and Air": "Транспорт: море та повітря",
    "Transportation - Land": "Транспорт: суходіл", "Bricks Curved": "Вигнуті цеглинки",
    "Flags, Banners and Signs": "Прапори, банери та знаки", "Magnets and Holders": "Магніти та тримачі",
    "Technic Panels": "Панелі Technic", "Large Buildable Figures": "Великі збірні фігури",
    "Belville, Scala and Fabuland": "Belville, Scala та Fabuland", "Znap": "Znap", "Mechanical": "Механіка",
    "Electronics": "Електроніка", "Technic Axles": "Осі Technic", "Windscreens and Fuselage": "Лобове скло та фюзеляж",
    "Clikits": "Clikits", "Plates Angled": "Клиноподібні пластини", "HO Scale": "Масштаб HO",
    "Technic Beams": "Балки Technic", "Technic Gears": "Шестерні Technic", "Technic Pins": "Штифти Technic",
    "Technic Bushes": "Втулки Technic", "Technic Beams Special": "Балки Technic спеціальні", "Tools": "Інструменти",
    "Non-Buildable Figures (Duplo, Fabuland, etc)": "Незбірні фігури (Duplo, Fabuland тощо)", "Stickers": "Наліпки",
    "Minifig Heads": "Голови мініфігурок", "Minifig Upper Body": "Торси мініфігурок",
    "Minifig Lower Body": "Ноги мініфігурок", "Minidoll Heads": "Голови мініляльок",
    "Minidoll Upper Body": "Торси мініляльок", "Minidoll Lower Body": "Ноги мініляльок",
    "Minifig Headwear": "Головні убори мініфігурок", "Modulex": "Modulex",
    "Tiles Round and Curved": "Круглі та вигнуті плитки", "Projectiles / Launchers": "Снаряди та пускові механізми",
    "Energy Effects": "Енергетичні ефекти", "Minifig Hipwear": "Пояси мініфігурок",
    "Minifig Neckwear": "Аксесуари на шию мініфігурок", "Minifig Headwear Accessories": "Аксесуари до головних уборів",
    "Minifig Shields, Weapons, & Tools": "Щити, зброя та інструменти",
    "Animal / Creature Accessories": "Аксесуари для тварин", "Animal / Creature Body Parts": "Частини тіла тварин",
    "Plants & Trees": "Рослини та дерева", "Non-System Parts": "Позасистемні деталі", "Pen & Watch": "Ручки та годинники",
}
