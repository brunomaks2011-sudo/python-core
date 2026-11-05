"""Build BRICK HUB catalog data files from the public Rebrickable catalogue.

This is a developer tool, it is NOT needed to run the shop.  It produces two
files that are committed to the repository:

* ``data/catalog_full.json.gz`` – the complete reference catalogue
  (colours, themes, part categories, ~62k parts, ~26k sets, ~17k minifigures).
  The shop imports it with ``manage.py import_catalog`` so that the admin panel
  can auto-fill names, years and piece counts by an official LEGO number and
  can warn about numbers that do not exist.
* ``data/catalog_seed.json`` – a curated subset that ``manage.py seed_demo``
  turns into shop listings (products) for a demo store.

Sources (all real data, nothing is invented here):

* Rebrickable catalogue (https://rebrickable.com/downloads/) as packaged in the
  ``lego-oracle`` npm package (SQLite file ``dist/data/lego.sqlite``).
* BrickLink colour ids/names as scraped in the ``bl-parts`` npm package
  (``dist/parts-data.json``).

Usage::

    python tools/build_catalog_data.py --sqlite path/to/lego.sqlite \
        --bl-colors path/to/parts-data.json --out data/

Ukrainian part names below are translations written for the shop; the official
English names always come from the catalogue.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Curated parts: (design id, shop category slug, Ukrainian name, base price UAH,
# number of colours to offer).  Design ids are verified against the catalogue at
# build time - unknown ids abort the build.
# ---------------------------------------------------------------------------
PARTS = [
    # Цеглинки
    ("3005", "tsehlynky", "Цеглинка 1 × 1", 2.5, 12),
    ("3004", "tsehlynky", "Цеглинка 1 × 2", 3.0, 12),
    ("3622", "tsehlynky", "Цеглинка 1 × 3", 3.5, 10),
    ("3010", "tsehlynky", "Цеглинка 1 × 4", 4.0, 10),
    ("3009", "tsehlynky", "Цеглинка 1 × 6", 5.5, 8),
    ("3008", "tsehlynky", "Цеглинка 1 × 8", 7.0, 8),
    ("3003", "tsehlynky", "Цеглинка 2 × 2", 4.0, 12),
    ("3002", "tsehlynky", "Цеглинка 2 × 3", 5.0, 10),
    ("3001", "tsehlynky", "Цеглинка 2 × 4", 6.0, 12),
    ("2456", "tsehlynky", "Цеглинка 2 × 6", 9.0, 8),
    ("2357", "tsehlynky", "Цеглинка 2 × 2 кутова", 5.0, 8),
    ("14716", "tsehlynky", "Цеглинка 1 × 1 × 3", 4.5, 6),
    ("3245c", "tsehlynky", "Цеглинка 1 × 2 × 2 з тримачем шипа", 5.0, 6),
    ("3062b", "tsehlynky", "Цеглинка кругла 1 × 1", 2.5, 10),
    ("3941", "tsehlynky", "Цеглинка кругла 2 × 2 з отвором під вісь", 5.0, 8),
    ("59900", "tsehlynky", "Конус 1 × 1", 3.0, 8),
    ("87087", "tsehlynky", "Цеглинка 1 × 1 з шипом збоку", 3.5, 8),
    ("11211", "tsehlynky", "Цеглинка 1 × 2 з двома шипами збоку", 4.5, 8),
    ("4070", "tsehlynky", "Цеглинка 1 × 1 «фара»", 3.5, 8),
    ("30136", "tsehlynky", "Цеглинка 1 × 2 «колода»", 3.5, 6),
    ("98283", "tsehlynky", "Цеглинка 1 × 2 з профілем кладки", 4.0, 6),
    ("54200", "tsehlynky", "Скіс 30° 1 × 1 × ⅔ («сирний»)", 2.5, 12),
    ("85984", "tsehlynky", "Скіс 30° 1 × 2 × ⅔", 3.0, 10),
    ("3039", "tsehlynky", "Скіс 45° 2 × 2", 4.5, 8),
    ("3040b", "tsehlynky", "Скіс 45° 2 × 1", 3.5, 8),
    ("3665", "tsehlynky", "Скіс обернений 45° 2 × 1", 3.5, 6),
    ("11477", "tsehlynky", "Скіс вигнутий 2 × 1 без шипів", 3.5, 10),
    ("15068", "tsehlynky", "Скіс вигнутий 2 × 2 × ⅔", 4.5, 10),
    ("93273", "tsehlynky", "Скіс вигнутий 4 × 1 подвійний", 6.0, 6),
    ("6091", "tsehlynky", "Цеглинка вигнута 1 × 2 × 1⅓", 4.5, 6),
    ("3659", "tsehlynky", "Арка 1 × 4", 6.0, 6),
    # Пластини
    ("3024", "plastyny", "Пластина 1 × 1", 1.5, 14),
    ("3023", "plastyny", "Пластина 1 × 2", 2.0, 14),
    ("3623", "plastyny", "Пластина 1 × 3", 2.5, 10),
    ("3710", "plastyny", "Пластина 1 × 4", 3.0, 12),
    ("3666", "plastyny", "Пластина 1 × 6", 4.0, 10),
    ("3460", "plastyny", "Пластина 1 × 8", 5.0, 8),
    ("3022", "plastyny", "Пластина 2 × 2", 3.0, 12),
    ("3021", "plastyny", "Пластина 2 × 3", 3.5, 10),
    ("3020", "plastyny", "Пластина 2 × 4", 4.0, 12),
    ("3795", "plastyny", "Пластина 2 × 6", 5.5, 10),
    ("3034", "plastyny", "Пластина 2 × 8", 7.0, 8),
    ("2420", "plastyny", "Пластина 2 × 2 кутова", 3.0, 8),
    ("3031", "plastyny", "Пластина 4 × 4", 9.0, 8),
    ("3032", "plastyny", "Пластина 4 × 6", 12.0, 8),
    ("15573", "plastyny", "Пластина 1 × 2 з одним шипом («джампер»)", 2.5, 10),
    ("87580", "plastyny", "Пластина 2 × 2 з центральним шипом («джампер»)", 3.5, 8),
    ("6141", "plastyny", "Пластина кругла 1 × 1", 1.5, 14),
    ("4032a", "plastyny", "Пластина кругла 2 × 2 з отвором під вісь", 3.0, 8),
    ("85861", "plastyny", "Пластина кругла 1 × 1 з відкритим шипом", 2.0, 8),
    ("99780", "plastyny", "Кронштейн 1 × 2 – 1 × 2 обернений", 4.0, 6),
    ("44728", "plastyny", "Кронштейн 1 × 2 – 2 × 2", 4.0, 6),
    ("60478", "plastyny", "Пластина 1 × 2 з ручкою на торці", 3.0, 6),
    ("4740", "plastyny", "Тарілка 2 × 2 обернена («радар»)", 3.5, 6),
    # Плитки
    ("3070b", "plytky", "Плитка 1 × 1", 2.0, 14),
    ("3069b", "plytky", "Плитка 1 × 2", 2.5, 14),
    ("63864", "plytky", "Плитка 1 × 3", 3.0, 10),
    ("2431", "plytky", "Плитка 1 × 4", 3.5, 12),
    ("6636", "plytky", "Плитка 1 × 6", 5.0, 8),
    ("4162", "plytky", "Плитка 1 × 8", 6.0, 8),
    ("3068b", "plytky", "Плитка 2 × 2", 3.5, 12),
    ("26603", "plytky", "Плитка 2 × 3", 4.5, 8),
    ("87079", "plytky", "Плитка 2 × 4", 5.5, 8),
    ("69729", "plytky", "Плитка 2 × 6", 7.0, 6),
    ("14719", "plytky", "Плитка 2 × 2 кутова", 4.0, 8),
    ("98138", "plytky", "Плитка кругла 1 × 1", 2.0, 14),
    ("14769", "plytky", "Плитка кругла 2 × 2", 4.0, 10),
    ("25269", "plytky", "Плитка кругла 1 × 1 (чверть)", 2.0, 8),
    ("24246", "plytky", "Плитка кругла 1 × 1 (половина)", 2.0, 8),
    ("2412b", "plytky", "Плитка 1 × 2 з решіткою", 3.0, 8),
    ("15712", "plytky", "Плитка 1 × 1 з кліпсою", 3.0, 8),
    ("27925", "plytky", "Плитка 2 × 2 вигнута («макарона»)", 4.0, 8),
    ("35787", "plytky", "Плитка 2 × 2 трикутна", 3.5, 8),
    # Колеса та шини
    ("55981", "kolesa-ta-shyny", "Колесо 18 × 14 з отвором під штифт", 9.0, 5),
    ("42610", "kolesa-ta-shyny", "Колесо 11 × 8", 5.0, 5),
    ("6014b", "kolesa-ta-shyny", "Колесо 11 × 12", 6.0, 4),
    ("56145", "kolesa-ta-shyny", "Колесо 30,4 × 20", 14.0, 4),
    ("34337", "kolesa-ta-shyny", "Колесо 8 × 6 з прорізом", 5.0, 4),
    ("13971", "kolesa-ta-shyny", "Колесо 18 × 8 з глибокими спицями", 9.0, 4),
    ("87697", "kolesa-ta-shyny", "Шина 21 × 12", 9.0, 2),
    ("59895", "kolesa-ta-shyny", "Шина 14 × 4 гладка", 4.0, 2),
    ("92402", "kolesa-ta-shyny", "Шина 30,4 × 14", 12.0, 2),
    ("50951", "kolesa-ta-shyny", "Шина 14 × 6 гладка", 4.5, 2),
    # Вікна та двері
    ("60592", "vikna-ta-dveri", "Вікно 1 × 2 × 2", 6.0, 6),
    ("60593", "vikna-ta-dveri", "Вікно 1 × 2 × 3", 7.0, 6),
    ("60594", "vikna-ta-dveri", "Вікно 1 × 4 × 3", 9.0, 6),
    ("60601", "vikna-ta-dveri", "Скло для вікна 1 × 2 × 2", 3.0, 3),
    ("60602", "vikna-ta-dveri", "Скло для вікна 1 × 2 × 3", 3.5, 3),
    ("60603", "vikna-ta-dveri", "Скло для вікна 1 × 4 × 3", 4.0, 3),
    ("57895", "vikna-ta-dveri", "Скло для вікна 1 × 4 × 6", 6.0, 3),
    ("60596", "vikna-ta-dveri", "Дверна рама 1 × 4 × 6", 12.0, 6),
    ("60616b", "vikna-ta-dveri", "Двері 1 × 4 × 6 гладкі", 12.0, 6),
    ("60623", "vikna-ta-dveri", "Двері 1 × 4 × 6 з чотирма шибками", 12.0, 6),
    ("30044", "vikna-ta-dveri", "Вікно 1 × 2 × 2⅔ з аркою", 7.0, 5),
    ("3823", "vikna-ta-dveri", "Лобове скло 2 × 4 × 2", 12.0, 4),
    ("35336", "vikna-ta-dveri", "Лобове скло 2 × 6 × 2", 14.0, 4),
    # Крила
    ("43722", "kryla", "Крило-пластина 3 × 2 праве", 3.5, 8),
    ("43723", "kryla", "Крило-пластина 3 × 2 ліве", 3.5, 8),
    ("41769", "kryla", "Крило-пластина 4 × 2 праве", 4.0, 8),
    ("41770", "kryla", "Крило-пластина 4 × 2 ліве", 4.0, 8),
    ("54383", "kryla", "Крило-пластина 6 × 3 праве", 6.0, 6),
    ("54384", "kryla", "Крило-пластина 6 × 3 ліве", 6.0, 6),
    ("51739", "kryla", "Клиноподібна пластина 2 × 4", 5.0, 8),
    ("2450", "kryla", "Клиноподібна пластина 3 × 3 зі зрізаним кутом", 4.5, 6),
    ("26601", "kryla", "Клиноподібна пластина 2 × 2 зі зрізаним кутом", 3.0, 8),
    ("47456", "kryla", "Клин вигнутий 2 × 3 × ⅔ з кінцем крила", 5.0, 6),
    ("47458", "kryla", "Клин вигнутий 1 × 2 × ⅔ з кінцем крила", 3.5, 6),
    ("2340", "kryla", "Хвостове крило 4 × 1 × 3", 6.0, 4),
    # Шестерні
    ("10928", "shesterni", "Шестерня Technic 8 зубців", 4.0, 3),
    ("3647", "shesterni", "Шестерня Technic 8 зубців (класична)", 4.0, 3),
    ("32270", "shesterni", "Шестерня Technic 12 зубців подвійна конічна", 5.0, 3),
    ("6589", "shesterni", "Шестерня Technic 12 зубців конічна", 4.5, 3),
    ("94925", "shesterni", "Шестерня Technic 16 зубців", 6.0, 3),
    ("18575", "shesterni", "Шестерня Technic 20 зубців подвійна конічна", 6.5, 3),
    ("32269", "shesterni", "Шестерня Technic 20 зубців подвійна конічна (X-отвір)", 6.5, 3),
    ("32198", "shesterni", "Шестерня Technic 20 зубців конічна", 6.0, 3),
    ("3648b", "shesterni", "Шестерня Technic 24 зубці", 7.0, 3),
    ("32498", "shesterni", "Шестерня Technic 36 зубців подвійна конічна", 10.0, 3),
    ("3649", "shesterni", "Шестерня Technic 40 зубців", 12.0, 3),
    ("3743", "shesterni", "Зубчаста рейка Technic 1 × 4", 4.0, 3),
    ("87761", "shesterni", "Зубчаста рейка Technic 1 × 7", 7.0, 3),
    ("32072", "shesterni", "Кулачкове колесо Technic", 4.0, 3),
    # Елементи Technic
    ("2780", "elementy-technic", "Штифт Technic з фрикцією", 1.0, 3),
    ("43093", "elementy-technic", "Вісь-штифт Technic з фрикцією", 1.5, 3),
    ("6558", "elementy-technic", "Штифт Technic довгий (3L) з фрикцією", 1.5, 3),
    ("3673", "elementy-technic", "Штифт Technic без фрикції", 1.0, 3),
    ("4274", "elementy-technic", "Штифт Technic ½", 1.0, 3),
    ("32062", "elementy-technic", "Вісь Technic 2L з насічкою", 1.5, 3),
    ("4519", "elementy-technic", "Вісь Technic 3L", 1.5, 3),
    ("3705", "elementy-technic", "Вісь Technic 4L", 2.0, 3),
    ("32073", "elementy-technic", "Вісь Technic 5L", 2.0, 3),
    ("3706", "elementy-technic", "Вісь Technic 6L", 2.5, 3),
    ("3707", "elementy-technic", "Вісь Technic 8L", 3.0, 3),
    ("3713", "elementy-technic", "Втулка Technic", 1.0, 3),
    ("32123b", "elementy-technic", "Втулка Technic ½", 1.0, 3),
    ("32523", "elementy-technic", "Балка Technic 1 × 3", 2.5, 6),
    ("32316", "elementy-technic", "Балка Technic 1 × 5", 3.5, 6),
    ("32524", "elementy-technic", "Балка Technic 1 × 7", 4.5, 6),
    ("40490", "elementy-technic", "Балка Technic 1 × 9", 5.5, 6),
    ("32525", "elementy-technic", "Балка Technic 1 × 11", 6.5, 6),
    ("41239", "elementy-technic", "Балка Technic 1 × 13", 7.5, 6),
    ("32278", "elementy-technic", "Балка Technic 1 × 15", 8.5, 6),
    ("32140", "elementy-technic", "Балка Technic L-подібна 2 × 4", 4.0, 5),
    ("32526", "elementy-technic", "Балка Technic L-подібна 3 × 5", 5.0, 5),
    ("60483", "elementy-technic", "Балка Technic 1 × 2 з отворами під штифт і вісь", 2.5, 5),
    ("3700", "elementy-technic", "Цеглинка Technic 1 × 2 з отвором", 3.5, 6),
    ("3701", "elementy-technic", "Цеглинка Technic 1 × 4", 5.0, 6),
    ("3894", "elementy-technic", "Цеглинка Technic 1 × 6", 6.5, 5),
    ("3702", "elementy-technic", "Цеглинка Technic 1 × 8", 8.0, 5),
    ("59443", "elementy-technic", "З'єднувач осей Technic", 2.5, 3),
    ("6536", "elementy-technic", "З'єднувач вісь-штифт Technic перпендикулярний", 2.5, 4),
    ("32013", "elementy-technic", "З'єднувач вісь-штифт Technic кутовий №1", 2.5, 4),
    ("64179", "elementy-technic", "Рама Technic 5 × 7", 12.0, 4),
    ("2736", "elementy-technic", "Вісь Technic з кулькою-фаркопом", 2.5, 2),
    # Рослини
    ("24866", "roslyny", "Квітка 1 × 1 з п'ятьма пелюстками", 2.0, 10),
    ("33291", "roslyny", "Квітка 1 × 1 з чотирма пелюстками", 2.0, 8),
    ("32607", "roslyny", "Пластина кругла 1 × 1 з трьома листками", 2.0, 6),
    ("2423", "roslyny", "Листя 4 × 3", 3.5, 6),
    ("2417", "roslyny", "Листя 6 × 5", 5.0, 5),
    ("37695", "roslyny", "Стебло з трьома листками", 3.0, 4),
    ("33183", "roslyny", "Морквяне бадилля", 2.0, 4),
    ("22667", "roslyny", "Вишні", 3.0, 4),
    ("30176", "roslyny", "Бамбукове листя 1 × 1", 2.5, 4),
    # Аксесуари для фігурок
    ("64567", "aksesuary-dlia-fihurok", "Руків'я світлового меча", 4.0, 6),
    ("30374", "aksesuary-dlia-fihurok", "Стрижень 4L (лезо світлового меча / паличка)", 3.0, 10),
    ("3899", "aksesuary-dlia-fihurok", "Чашка", 3.0, 8),
    ("2343", "aksesuary-dlia-fihurok", "Келих", 3.0, 6),
    ("30162", "aksesuary-dlia-fihurok", "Бінокль", 4.0, 4),
    ("4006", "aksesuary-dlia-fihurok", "Викрутка й гайковий ключ", 4.0, 4),
    ("21459", "aksesuary-dlia-fihurok", "Меч / катана", 5.0, 5),
    ("36752a", "aksesuary-dlia-fihurok", "Чарівна паличка", 4.0, 4),
    ("4522", "aksesuary-dlia-fihurok", "Молот", 4.0, 4),
    ("92738", "aksesuary-dlia-fihurok", "Бластер малий (Star Wars)", 5.0, 3),
    ("58247", "aksesuary-dlia-fihurok", "Бластер короткий (Star Wars)", 5.0, 3),
    ("2446", "aksesuary-dlia-fihurok", "Шолом стандартний", 6.0, 6),
    ("39262", "aksesuary-dlia-fihurok", "Корона / квітка / шкаралупа", 4.0, 6),
    # Інші елементи
    ("3937", "inshi-elementy", "Шарнірна цеглинка 1 × 2 (основа)", 3.0, 6),
    ("6134", "inshi-elementy", "Шарнірна цеглинка 2 × 2 (верх)", 3.0, 6),
    ("3680", "inshi-elementy", "Поворотна платформа 2 × 2 (основа)", 3.0, 5),
    ("3679", "inshi-elementy", "Поворотна платформа 2 × 2 (верх)", 3.0, 5),
    ("87994", "inshi-elementy", "Стрижень 3L", 2.0, 6),
    ("4865b", "inshi-elementy", "Панель 1 × 2 × 1", 3.0, 8),
    ("87552", "inshi-elementy", "Панель 1 × 2 × 2", 4.0, 8),
    ("6231", "inshi-elementy", "Панель 1 × 1 × 1 кутова", 3.0, 6),
    ("3633", "inshi-elementy", "Паркан 1 × 4 × 1 решітчастий", 4.0, 6),
]

# Shop series -> Rebrickable root theme ids (sub-themes are included).
SET_SERIES = [
    ("city", [52]),
    ("technic", [1]),
    ("star-wars", [158]),
    ("icons", [721, 155]),
    ("creator", [22]),
    ("speed-champions", [601]),
    ("harry-potter", [246]),
    ("ninjago", [435]),
    ("marvel", [696]),
    ("minecraft", [577]),
    ("friends", [494]),
    ("architecture", [252]),
    ("ideas", [576]),
    ("super-mario", [690]),
]
OTHER_SET_SERIES = [
    ("jurassic-world", [602]),
    ("disney", [608]),
    ("dc", [695]),
    ("botanicals", [769]),
    ("dreamzzz", [749]),
    ("lego-art", [709]),
]
MINIFIG_SERIES = [
    ("star-wars", [158]),
    ("marvel", [696]),
    ("harry-potter", [246]),
    ("ninjago", [435]),
    ("city", [52]),
    ("dc", [695]),
    ("collectible-minifigures", [535]),
]
OTHER_MINIFIG_SERIES = [("jurassic-world", [602]), ("minecraft", [577]), ("disney", [608])]

EXCLUDE_WORDS = re.compile(
    r"\b(key ?chain|magnet|bundle|collection|kit|value pack|super pack|combo|bonus|"
    r"polybag|promo|book|game|watch|calendar|storage|minifigure pack|figure pack)\b",
    re.I,
)
SET_NUM_RE = re.compile(r"^\d{4,6}-1$")

# BrickLink uses "Satin" where Rebrickable says "Opal" for the same colours.
BL_ALIASES = {
    "satin trans-light blue": "opal trans-light blue",
    "satin trans-clear": "opal trans-clear",
    "satin trans-dark blue": "opal trans-dark blue",
    "satin trans-bright green": "opal trans-bright green",
    "satin trans-purple": "opal trans-purple",
}


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def theme_tree(con):
    parent = {r["id"]: r["parent_id"] for r in con.execute("select id, parent_id from themes")}

    def root_of(tid):
        seen = set()
        while parent.get(tid) is not None and tid not in seen:
            seen.add(tid)
            tid = parent[tid]
        return tid

    def subtree(roots):
        out = set(roots)
        changed = True
        while changed:
            changed = False
            for tid, pid in parent.items():
                if pid in out and tid not in out:
                    out.add(tid)
                    changed = True
        return out

    return parent, root_of, subtree


def bricklink_colors(path: str | None) -> dict[str, int]:
    if not path:
        return {}
    out = {}
    for part in json.loads(Path(path).read_text()):
        for c in part["colors"]:
            name = c["colorName"].lower()
            out[BL_ALIASES.get(name, name)] = int(c["colorId"])
    return out


def build_full(con, bl):
    colors = []
    for r in con.execute("select id, name, rgb, is_trans from colors order by id"):
        colors.append([r["id"], r["name"], r["rgb"], int(r["is_trans"]), bl.get(r["name"].lower())])
    themes = [[r["id"], r["name"], r["parent_id"]] for r in con.execute("select * from themes order by id")]
    cats = [[r["id"], r["name"]] for r in con.execute("select * from part_categories order by id")]
    parts = [
        [r["part_num"], r["name"], r["part_cat_id"]]
        for r in con.execute("select part_num, name, part_cat_id from parts order by part_num")
    ]
    figs_per_set = defaultdict(int)
    first_inv = {}
    for r in con.execute("select id, set_num, version from inventories order by version"):
        first_inv.setdefault(r["set_num"], r["id"])
    inv_to_set = {v: k for k, v in first_inv.items()}
    for r in con.execute("select inventory_id, quantity from inventory_minifigs"):
        s = inv_to_set.get(r["inventory_id"])
        if s:
            figs_per_set[s] += r["quantity"]
    sets = []
    for r in con.execute("select * from sets order by set_num"):
        has_img = 1 if r["img_url"] == f"https://cdn.rebrickable.com/media/sets/{r['set_num'].lower()}.jpg" else 0
        sets.append([r["set_num"], r["name"], r["year"], r["theme_id"], r["num_parts"], figs_per_set.get(r["set_num"], 0), has_img])
    figs = []
    for r in con.execute("select * from minifigs order by fig_num"):
        figs.append([r["fig_num"], r["name"], r["num_parts"]])
    return {
        "format": 1,
        "source": "Rebrickable catalogue (rebrickable.com) via lego-oracle 0.1.2; BrickLink colour ids via bl-parts 1.0.2",
        "image_base": "https://cdn.rebrickable.com/media/sets/",
        "colors": colors,
        "themes": themes,
        "part_categories": cats,
        "parts": parts,
        "sets": sets,
        "minifigs": figs,
    }, figs_per_set


def build_seed(con, bl, figs_per_set):
    parent, root_of, subtree = theme_tree(con)
    color_rows = {r["id"]: r for r in con.execute("select * from colors")}

    # ---- parts and their most used colours (sets from 2015+) ----
    part_rows = {r["part_num"]: r for r in con.execute("select * from parts")}
    missing = [p[0] for p in PARTS if p[0] not in part_rows]
    if missing:
        raise SystemExit(f"Unknown design ids in curation list: {missing}")
    wanted = {p[0] for p in PARTS}
    usage = defaultdict(Counter)
    q = (
        "select ip.part_num, ip.color_id, count(distinct i.set_num) n from inventory_parts ip "
        "join inventories i on i.id = ip.inventory_id join sets s on s.set_num = i.set_num "
        "where s.year >= 2015 and ip.is_spare = 0 and ip.part_num in (%s) group by ip.part_num, ip.color_id"
    ) % ",".join("?" * len(wanted))
    for r in con.execute(q, sorted(wanted)):
        if r["color_id"] in (-1, 9999):
            continue
        usage[r["part_num"]][r["color_id"]] = r["n"]
    # classic parts that left modern sets: fall back to their whole history
    old = sorted(d for d in wanted if not usage[d])
    if old:
        q_all = q.replace("s.year >= 2015 and ", "").replace("(%s)" % ",".join("?" * len(wanted)), "(%s)" % ",".join("?" * len(old)))
        for r in con.execute(q_all, old):
            if r["color_id"] not in (-1, 9999):
                usage[r["part_num"]][r["color_id"]] = r["n"]
    parts = []
    for design, cat, name_uk, price, n_colors in PARTS:
        common = [cid for cid, _ in usage[design].most_common(n_colors)]
        if not common:
            raise SystemExit(f"No colour usage for {design}")
        parts.append(
            {
                "design_id": design,
                "name": part_rows[design]["name"],
                "rb_category": part_rows[design]["part_cat_id"],
                "shop_category": cat,
                "name_uk": name_uk,
                "base_price": price,
                "colors": common,
                "set_count": sum(usage[design].values()),
            }
        )

    # ---- sets ----
    all_sets = [dict(r) for r in con.execute("select * from sets")]

    def pick_sets(roots, n_big, n_recent, years=(2020, 2026)):
        themes = subtree(roots)
        cands = [
            s for s in all_sets
            if s["theme_id"] in themes and SET_NUM_RE.match(s["set_num"])
            and years[0] <= (s["year"] or 0) <= years[1] and (s["num_parts"] or 0) >= 40
            and not EXCLUDE_WORDS.search(s["name"])
        ]
        big = sorted(cands, key=lambda s: -s["num_parts"])[:n_big]
        chosen = {s["set_num"] for s in big}
        recent = [s for s in sorted(cands, key=lambda s: (-s["year"], -s["num_parts"])) if s["set_num"] not in chosen]
        # spread recent picks over the size range so the shop has small and medium sets too
        recent = recent[: n_recent * 3][::3] if len(recent) > n_recent * 3 else recent[:n_recent]
        return big + recent[:n_recent]

    sets_out = []
    seen = set()

    def add(series, s, **extra):
        if s["set_num"] in seen:
            return
        seen.add(s["set_num"])
        sets_out.append(
            {
                "number": s["set_num"],
                "name": s["name"],
                "year": s["year"],
                "rb_theme": s["theme_id"],
                "rb_root_theme": root_of(s["theme_id"]),
                "pieces": s["num_parts"],
                "minifigs": figs_per_set.get(s["set_num"], 0),
                "img_url": s["img_url"],
                "series": series,
                **extra,
            }
        )

    for slug, roots in SET_SERIES:
        for s in pick_sets(roots, 6, 12):
            add(slug, s)
    for slug, roots in OTHER_SET_SERIES:
        for s in pick_sets(roots, 2, 2):
            add(slug, s)
    # rare & collectible: retired flagships
    rare_roots = [158, 721, 155, 22, 576, 246, 1]
    series_of_root = {r: slug for slug, roots in SET_SERIES for r in roots}
    rare = [
        s for s in all_sets
        if root_of(s["theme_id"]) in rare_roots and SET_NUM_RE.match(s["set_num"])
        and 2007 <= (s["year"] or 0) <= 2019 and (s["num_parts"] or 0) >= 2400
        and not EXCLUDE_WORDS.search(s["name"])
    ]
    for s in sorted(rare, key=lambda s: -s["num_parts"])[:12]:
        add(series_of_root[root_of(s["theme_id"])], s, rare=True)
    # second-hand stock: mid-size sets from 2016-2021
    used = [
        s for s in all_sets
        if root_of(s["theme_id"]) in series_of_root and SET_NUM_RE.match(s["set_num"])
        and 2016 <= (s["year"] or 0) <= 2021 and 250 <= (s["num_parts"] or 0) <= 1500
        and not EXCLUDE_WORDS.search(s["name"])
    ]
    used.sort(key=lambda s: (s["set_num"]))
    for s in used[::max(1, len(used) // 18)][:18]:
        add(series_of_root[root_of(s["theme_id"])], s, used_only=True)

    # ---- accessories (LEGO gear) ----
    gear = subtree([501])
    acc = [
        s for s in all_sets
        if s["theme_id"] in gear and (s["year"] or 0) >= 2019 and s["img_url"]
        and re.match(r"^\d{5,8}-1$", s["set_num"])
        and re.search(r"storage (brick|box|head)|key ?chain|brick separator|display", s["name"], re.I)
        and not re.search(r"felt|light|poster|bag", s["name"], re.I)
    ]
    acc.sort(key=lambda s: (-s["year"], s["name"]))
    accessories, names = [], set()
    for s in acc:
        key = re.sub(r"\(.*?\)", "", s["name"]).strip().lower()
        if key in names:
            continue
        names.add(key)
        accessories.append({"number": s["set_num"], "name": s["name"], "year": s["year"], "img_url": s["img_url"],
                            "rb_theme": s["theme_id"]})
        if len(accessories) >= 16:
            break

    # ---- minifigures ----
    inv_set = {r["id"]: r["set_num"] for r in con.execute("select id, set_num from inventories")}
    set_info = {s["set_num"]: s for s in all_sets}
    fig_sets = defaultdict(set)
    for r in con.execute("select inventory_id, fig_num from inventory_minifigs"):
        s = inv_set.get(r["inventory_id"])
        if s in set_info:
            fig_sets[r["fig_num"]].add(s)
    fig_rows = {r["fig_num"]: dict(r) for r in con.execute("select * from minifigs")}

    def pick_figs(roots, n, min_year):
        themes = subtree(roots)
        scored = []
        for fig, sets_ in fig_sets.items():
            in_theme = [s for s in sets_ if set_info[s]["theme_id"] in themes]
            if not in_theme:
                continue
            years = [set_info[s]["year"] for s in in_theme]
            if max(years) < min_year:
                continue
            f = fig_rows.get(fig)
            if not f or (f["num_parts"] or 0) < 3:
                continue
            scored.append((len(in_theme), max(years), fig, min(years)))
        scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
        out, names_ = [], set()
        for cnt, ymax, fig, ymin in scored:
            base = re.split(r" - |,", fig_rows[fig]["name"])[0].strip().lower()
            if base in names_:
                continue
            names_.add(base)
            out.append((fig, ymin, cnt))
            if len(out) >= n:
                break
        return out

    minifigs = []
    fig_seen = set()
    for slug, roots in MINIFIG_SERIES + OTHER_MINIFIG_SERIES:
        n = 16 if (slug, roots) in MINIFIG_SERIES else 5
        for fig, year, cnt in pick_figs(roots, n, 2021 if slug == "collectible-minifigures" else 2019):
            if fig in fig_seen:
                continue
            fig_seen.add(fig)
            f = fig_rows[fig]
            minifigs.append({"fig_num": fig, "name": f["name"], "num_parts": f["num_parts"], "img_url": f["img_url"],
                             "series": slug, "year": year, "set_count": cnt,
                             "appears_in": sorted(s for s in fig_sets[fig] if SET_NUM_RE.match(s))[:6]})
    # contents (комплектація) from the minifigure's own inventory
    fig_inv = {}
    for r in con.execute("select id, set_num from inventories order by version"):
        if r["set_num"] in fig_seen:
            fig_inv.setdefault(r["set_num"], r["id"])
    inv_fig = {v: k for k, v in fig_inv.items()}
    contents = defaultdict(list)
    if inv_fig:
        q = ("select ip.inventory_id, ip.part_num, p.name pname, ip.color_id, ip.quantity from inventory_parts ip "
             "join parts p on p.part_num = ip.part_num where ip.is_spare = 0 and ip.inventory_id in (%s)") % ",".join(
            "?" * len(inv_fig))
        for r in con.execute(q, list(inv_fig)):
            contents[inv_fig[r["inventory_id"]]].append([r["part_num"], r["pname"], r["color_id"], r["quantity"]])
    for m in minifigs:
        m["contents"] = contents.get(m["fig_num"], [])

    used_colors = {c for p in parts for c in p["colors"]} | {row[2] for m in minifigs for row in m["contents"]}
    used_themes = set()
    for s in sets_out + accessories:
        t = s["rb_theme"]
        while t is not None:
            used_themes.add(t)
            t = parent.get(t)
    return {
        "format": 1,
        "source": "Rebrickable catalogue (rebrickable.com) via lego-oracle 0.1.2; BrickLink colour ids via bl-parts 1.0.2",
        "parts": parts,
        "sets": sets_out,
        "accessories": accessories,
        "minifigs": minifigs,
        "used_colors": sorted(used_colors),
        "used_themes": sorted(used_themes),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True)
    ap.add_argument("--bl-colors")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data"))
    args = ap.parse_args()
    con = connect(args.sqlite)
    bl = bricklink_colors(args.bl_colors)
    full, figs_per_set = build_full(con, bl)
    seed = build_seed(con, bl, figs_per_set)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with gzip.open(out / "catalog_full.json.gz", "wt", encoding="utf-8", compresslevel=9) as fh:
        json.dump(full, fh, ensure_ascii=False, separators=(",", ":"))
    (out / "catalog_seed.json").write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"full: {len(full['colors'])} colours ({sum(1 for c in full['colors'] if c[4])} with BrickLink id), "
        f"{len(full['themes'])} themes, {len(full['parts'])} parts, {len(full['sets'])} sets, {len(full['minifigs'])} minifigs"
    )
    print(
        f"seed: {len(seed['parts'])} part designs / {sum(len(p['colors']) for p in seed['parts'])} part listings, "
        f"{len(seed['sets'])} sets, {len(seed['accessories'])} accessories, {len(seed['minifigs'])} minifigs"
    )


if __name__ == "__main__":
    main()
