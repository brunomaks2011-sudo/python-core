"""Starting points a draft can be built from, with labels and recolourable roles.

Every template is something LDraw Nova can already build and check: a vehicle
recipe (`vehicle plan`), a reviewed example plan shipped with LDraw Nova, or a
parametric generator from this package. Labels are Russian because the site
is; Claude still answers in the language of the request.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["vehicle", "example", "generator"]

NOVA_ATTRIBUTION = ("Licensed under CC BY-SA 4.0 : adapted from the ldraw-nova examples "
                    "by Carlos Antelo, github.com/anteloc/ldraw-nova")

# The six requests from the brief, shown as chips on the start page.
THEMES = [
    ("Спортивная машина", "красная спортивная машина"),
    ("Экскаватор", "жёлтый экскаватор"),
    ("Робот", "робот"),
    ("Самолёт", "самолёт"),
    ("Космический корабль", "космический корабль"),
    ("Дом", "дом"),
]


@dataclass(frozen=True)
class Colour:
    name: str  # LDConfig name, used as @colours.<name>
    label: str
    hex: str
    stems: tuple[str, ...] = ()  # words that select it in the rule-based planner


# Common solid colours a user can ask for. Names are verified against LDConfig.
COLOURS: dict[str, Colour] = {c.name: c for c in [
    Colour("Red", "красный", "#B40000", ("красн", "red")),
    Colour("Dark_Red", "тёмно-красный", "#720012", ("бордов", "вишн", "dark red", "maroon")),
    Colour("Orange", "оранжевый", "#D67923", ("оранж", "orange")),
    Colour("Dark_Orange", "тёмно-оранжевый", "#91501C", ("рыж", "dark orange")),
    Colour("Yellow", "жёлтый", "#FAC80A", ("желт", "yellow")),
    Colour("Bright_Light_Yellow", "светло-жёлтый", "#FFEC6C", ("лимон", "light yellow")),
    Colour("Lime", "салатовый", "#A5CA18", ("салат", "лайм", "lime")),
    Colour("Green", "зелёный", "#00852B", ("зелен", "green")),
    Colour("Dark_Green", "тёмно-зелёный", "#00451A", ("изумруд", "dark green")),
    Colour("Sand_Green", "серо-зелёный", "#708E7C", ("олив", "хаки", "khaki", "olive")),
    Colour("Blue", "синий", "#1E5AA8", ("син", "blue")),
    Colour("Dark_Blue", "тёмно-синий", "#19325A", ("темно-син", "navy", "dark blue")),
    Colour("Medium_Azure", "голубой", "#68C3E2", ("голуб", "light blue", "azure")),
    Colour("Dark_Turquoise", "бирюзовый", "#069D9F", ("бирюз", "turquoise", "teal")),
    Colour("Bright_Pink", "розовый", "#FF9ECD", ("розов", "pink")),
    Colour("Magenta", "малиновый", "#901F76", ("малин", "magenta")),
    Colour("Medium_Lavender", "фиолетовый", "#A06EB9", ("фиолет", "сирен", "purple", "violet")),
    Colour("White", "белый", "#F4F4F4", ("бел", "white")),
    Colour("Light_Bluish_Grey", "светло-серый", "#969696", ("сер", "grey", "gray")),
    Colour("Dark_Bluish_Grey", "тёмно-серый", "#646464", ("графит", "темно-сер", "dark grey", "dark gray")),
    Colour("Black", "чёрный", "#1B2A34", ("черн", "black")),
    Colour("Tan", "бежевый", "#D7BA8C", ("беж", "песочн", "tan", "beige", "sand")),
    Colour("Reddish_Brown", "коричневый", "#5F3109", ("коричн", "brown", "wood")),
    Colour("Pearl_Gold", "золотой", "#AA7F2E", ("золот", "gold")),
    Colour("Flat_Silver", "серебристый", "#8C8C8C", ("серебр", "silver", "metal")),
]}


@dataclass(frozen=True)
class Role:
    """A part of the model the user may recolour.

    For vehicles `source` is the palette role whose colour is replaced; for
    examples it is the LDraw colour code used by that part of the source plan,
    optionally limited to some sections. Generators take the colour directly.
    """
    key: str
    label: str
    source: str | int = ""
    sections: tuple[str, ...] = ()


@dataclass(frozen=True)
class Palette:
    key: str
    label: str


VEHICLE_PALETTES = (
    Palette("heritage-racing", "классика гонок: тёмно-зелёный с бежевым"),
    Palette("coastal-delivery", "побережье: серо-голубой с белым"),
    Palette("desert-utility", "пустыня: тёмно-оранжевый с бежевым"),
)


@dataclass(frozen=True)
class Template:
    key: str
    kind: Kind
    title: str
    summary: str
    keywords: tuple[str, ...]
    source: str  # vehicle recipe name, example plan path inside LDraw Nova, or generator name
    roles: tuple[Role, ...] = ()
    palettes: tuple[Palette, ...] = ()
    default_palette: str | None = None
    attribution: str | None = NOVA_ATTRIBUTION
    # Stems that strongly identify this template outrank shared words such as "дом".
    strong: tuple[str, ...] = field(default_factory=tuple)

    def role(self, key: str) -> Role | None:
        return next((r for r in self.roles if r.key == key), None)

    def palette(self, key: str | None) -> Palette | None:
        return next((p for p in self.palettes if p.key == key), None)


def _vehicle(key, title, summary, keywords, palette, roles=(("body", "кузов", "body"), ("roof", "крыша", "roof")), strong=()):
    return Template(key, "vehicle", title, summary, keywords, key,
                    roles=tuple(Role(k, label, source) for k, label, source in roles),
                    palettes=VEHICLE_PALETTES, default_palette=palette, strong=strong)


def _building(key, title, summary, keywords, roles=(), strong=()):
    return Template(key, "example", title, summary, keywords,
                    f"examples/building-atlas/{key}/scene.plan.json", roles=roles, strong=strong)


TEMPLATES: dict[str, Template] = {t.key: t for t in [
    # Vehicles: LDraw Nova recipes with matched wheels, glazing and fittings.
    _vehicle("grand-tourer", "Спортивная машина (гран-туризмо)",
             "Длинный капот, низкая кабина и короткая корма; колёса на настоящих осях.",
             ("машин", "авто", "спорт", "гонк", "гоноч", "купе", "кабриолет", "легков", "тачк", "car", "sport", "racing", "coupe", "auto"),
             "heritage-racing", strong=("спорт", "гоноч", "гонк", "sport", "racing")),
    _vehicle("delivery-van", "Фургон доставки",
             "Короткий капот, высокая кабина и грузовой кузов.",
             ("фургон", "доставк", "минивэн", "автобус", "van", "delivery", "bus"), "coastal-delivery",
             strong=("фургон", "van")),
    _vehicle("pickup", "Пикап",
             "Отдельная кабина и открытый кузов с бортами.",
             ("пикап", "внедорож", "джип", "pickup", "pick-up", "jeep", "suv"), "desert-utility",
             strong=("пикап", "pickup")),
    _vehicle("tipper-truck", "Самосвал",
             "Строительный грузовик с кабиной впереди и опрокидывающимся кузовом.",
             ("самосвал", "грузовик", "стройк", "строит", "фур", "truck", "tipper", "dump", "lorry"), "desert-utility",
             strong=("самосвал", "грузовик", "truck", "tipper", "пожарная машина", "fire truck", "fire engine")),
    _vehicle("touring-motorcycle", "Мотоцикл",
             "Мотоциклетная рама, обтекатель, спицованные колёса и багажник.",
             ("мотоцикл", "байк", "мопед", "скутер", "motorcycle", "motorbike", "bike", "scooter"), "heritage-racing",
             roles=(("body", "бак и обтекатель", "body"),), strong=("мотоцикл", "motorcycle")),
    _vehicle("harbour-launch", "Катер",
             "Корпус лодки, открытая рубка с сиденьем и штурвалом, ходовые огни.",
             ("катер", "лодк", "яхт", "судн", "корабл", "boat", "ship", "yacht"), "coastal-delivery",
             roles=(), strong=("катер", "лодк", "яхт", "boat")),
    _vehicle("courier-jet", "Самолёт (бизнес-джет)",
             "Обтекаемый нос с остеклением, стреловидные крылья, двигатели на пилонах и Т-образное хвостовое оперение.",
             ("самол", "джет", "авиа", "лайнер", "истребител", "plane", "jet", "aircraft", "airplane", "airliner"),
             "coastal-delivery",
             roles=(("fuselage", "фюзеляж", "roof"), ("wings", "крылья", "body")),
             strong=("самол", "plane", "jet", "aircraft")),

    # Spaceship: the reviewed SNOT reference design.
    Template("halcyon", "example", "Космический истребитель «Халкион»",
             "SNOT-конструкция: прочный каркас, боковые обшивки, два двигателя и стойка-подставка.",
             ("косми", "звездол", "корабл", "ракет", "шаттл", "истребител", "space", "starship", "starfighter", "rocket", "shuttle", "ufo", "нло"),
             "examples/snot/halcyon/halcyon.plan.json",
             roles=(Role("hull", "корпус", 15), Role("accent", "полосы и акценты", 321)),
             strong=("косми", "звездол", "space", "star")),

    # Buildings: reviewed minifigure-scale scenes from the LDraw Nova building atlas.
    _building("cottage", "Дом с верандой",
              "Двускатная крыша, веранда у входа, дерево, скамейка и цветы на участке 32×32.",
              ("дом", "домик", "коттедж", "дач", "изб", "house", "home", "cottage"),
              roles=(Role("walls", "стены", 19, ("cottage-shell.ldr", "cottage-shell-roof.ldr")),
                     Role("roof", "крыша", 72, ("cottage-shell-roof.ldr", "porch-15-72-8-4-144.ldr")))),
    _building("winter-lodge", "Альпийское шале",
              "Деревянный дом со снегом на крыше, крыльцом и ёлкой.",
              ("шале", "зимн", "горн", "лыж", "снег", "lodge", "chalet", "alpine", "winter"), strong=("шале", "chalet")),
    _building("farmstead", "Ферма с красным амбаром",
              "Амбар, зернохранилище, забор и огород.",
              ("ферм", "амбар", "сарай", "деревенск", "farm", "barn"), strong=("ферм", "амбар", "farm", "barn")),
    _building("lighthouse", "Маяк с домиком смотрителя",
              "Полосатая башня маяка и маленький дом рядом.",
              ("маяк", "lighthouse"), strong=("маяк", "lighthouse")),
    _building("fire-station", "Пожарная часть",
              "Широкие ворота для машин, башня для рукавов и красно-белые полосы.",
              ("пожар", "депо", "fire"),
              strong=("пожарная часть", "пожарное депо", "пожарная станция", "fire station", "firehouse")),
    _building("school", "Школа с внутренним двором",
              "Корпус с классами, башня с часами и двор.",
              ("школ", "school"), strong=("школ", "school")),
    _building("clinic", "Поликлиника",
              "Низкое крыло, остеклённый вестибюль и медицинский знак.",
              ("больниц", "клиник", "поликлин", "госпитал", "hospital", "clinic"), strong=("больниц", "клиник", "hospital", "clinic")),
    _building("museum", "Музей с портиком",
              "Симметричный фасад, колоннада и фронтон.",
              ("музей", "театр", "дворец", "museum", "theatre", "palace"), strong=("музей", "museum")),
    _building("market-court", "Рыночная площадь",
              "Два магазина и прилавок вокруг пешеходного двора.",
              ("рын", "магазин", "лавк", "кафе", "market", "shop", "store", "cafe"), strong=("рын", "магазин", "market", "shop")),
    _building("workshop", "Ремонтная мастерская",
              "Мастерская с воротами, двором и инструментами.",
              ("мастерск", "гараж", "автосервис", "завод", "workshop", "garage", "factory"), strong=("мастерск", "гараж", "garage", "workshop")),
    _building("railway-station", "Железнодорожная станция",
              "Платформа с навесом и зданием вокзала.",
              ("вокзал", "станци", "поезд", "железн", "station", "train", "railway"), strong=("вокзал", "поезд", "train", "railway")),
    _building("gatehouse", "Крепостные ворота",
              "Две башни и арка ворот, как у средневекового замка.",
              ("замок", "крепост", "башн", "рыцар", "castle", "fort", "knight"), strong=("замок", "крепост", "castle")),
    _building("medieval-village", "Средневековая деревня",
              "Несколько фахверковых домов вдоль улицы.",
              ("деревн", "средневек", "village", "medieval"), strong=("деревн", "village")),
    _building("temple", "Пагода",
              "Многоярусная крыша, колонны и лестница.",
              ("храм", "пагод", "китай", "япон", "temple", "pagoda"), strong=("пагод", "pagoda")),
    _building("conservatory", "Оранжерея",
              "Стеклянный павильон для растений.",
              ("оранжере", "теплиц", "сад", "greenhouse", "conservatory", "garden"), strong=("оранжере", "теплиц", "greenhouse")),
    _building("treehouse", "Домик на дереве",
              "Платформа на дереве, хижина и лестница.",
              ("на дереве", "дерев", "treehouse", "tree house"), strong=("на дереве", "treehouse")),
    _building("wizard-tower", "Башня волшебника",
              "Обсерватория с конической крышей и шпилем.",
              ("волшеб", "маг", "колдун", "сказоч", "wizard", "magic", "fairy"), strong=("волшеб", "wizard")),
    _building("moon-base", "Лунная база",
              "Жилые модули, переход, антенна и солнечные панели.",
              ("лун", "марс", "база", "станци", "moon", "mars", "base", "colony"), strong=("лун", "марс", "moon", "mars")),
    _building("skyline", "Микрогород",
              "Небоскрёбы и мосты в микромасштабе.",
              ("город", "небоскр", "мегапол", "city", "skyline", "skyscraper"), strong=("небоскр", "skyline", "skyscraper")),
    _building("frontier", "Торговый пост на Диком Западе",
              "Деревянные постройки в стиле вестерна.",
              ("вестерн", "запад", "ковбо", "салун", "western", "cowboy", "saloon"), strong=("вестерн", "ковбо", "western", "cowboy")),
    _building("desert-sanctuary", "Святилище в пустыне",
              "Руины древнего храма среди песка.",
              ("пустын", "руин", "пирамид", "древн", "desert", "ruin", "pyramid", "ancient"), strong=("пустын", "руин", "desert", "ruin")),

    # Parametric generators written for this site: LDraw Nova has no recipe for these.
    Template("excavator", "generator", "Гусеничный экскаватор",
             "Гусеничная тележка, поворотная платформа с кабиной и противовесом, стрела, рукоять и ковш.",
             ("экскават", "копател", "ковш", "трактор", "бульдозер", "excavator", "digger", "bulldozer", "tractor"),
             "excavator",
             roles=(Role("body", "корпус и стрела"), Role("tracks", "гусеницы"), Role("cab", "кабина")),
             attribution=None, strong=("экскават", "excavator", "digger")),
    Template("robot", "generator", "Робот",
             "Робот из кубиков: ноги с круглыми коленями, корпус с огоньками, руки и квадратная голова с лицом, ушами и антенной.",
             ("робот", "андроид", "дроид", "киборг", "мех", "трансформер", "robot", "android", "droid", "mech", "cyborg"),
             "robot",
             roles=(Role("body", "корпус"), Role("limbs", "руки и ноги"), Role("accent", "акценты")),
             attribution=None, strong=("робот", "robot", "дроид", "droid")),
]}


def describe_for_model() -> str:
    """The catalog as compact text for the planner's system prompt."""
    lines = []
    for t in TEMPLATES.values():
        roles = ", ".join(f"{r.key} ({r.label})" for r in t.roles) or "none"
        palettes = ", ".join(p.key for p in t.palettes)
        line = f"- {t.key}: {t.title}. {t.summary} Recolourable roles: {roles}."
        if palettes:
            line += f" Palettes: {palettes} (default {t.default_palette})."
        lines.append(line)
    return "\n".join(lines)
