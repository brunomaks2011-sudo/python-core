"""Name and shop section for a number typed in the panel that is not in the local catalogue.

The owner types the BrickLink number (e.g. a printed torso 973pb1234c01) and the shop fills in the rest:
1. it asks BrickLink's catalogue page for the official name and category (when the server may reach BrickLink;
   the answer is cached), and puts the part into the matching shop section;
2. otherwise it uses the base part of the number from the local catalogue (973 → torsos) for the section and
   the name.
Pictures always come from BrickLink by the number itself (see bricklink.py).
"""
from __future__ import annotations

import html
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

from django.core.cache import cache
from django.db.models import Count

from .models import Category, Element, Part, Theme

logger = logging.getLogger("brickhub")

CATALOG_PAGE = "https://www.bricklink.com/v2/catalog/catalogitem.page?{}"
TITLE_RE = re.compile(r"<title>\s*BrickLink\s*-\s*(?:Part|Minifig|Minifigure|Set|Gear|Book)\s+(?P<no>[^:<]+?)\s*:\s*"
                      r"(?P<rest>.*?)\s*-\s*BrickLink Reference Catalog\s*</title>", re.S | re.I)
OFFLINE_KEY = "bricklink:offline"

# BrickLink category (from the page title) → shop section; the first rule that matches wins
SECTION_RULES = [
    ("torso", "torsy"), ("headgear", "kapeliukhy-ta-masky"), ("headwear", "kapeliukhy-ta-masky"),
    ("minifigure, head", "holovy"), ("minifig, head", "holovy"), ("legs", "nohy"),
    ("hips", "nohy"), ("hair", "volossia"), ("helmet", "sholomy"), ("shield", "shchyty"), ("weapon", "zbroia"), ("utensil", "predmety-ta-obladnannia"),
    ("body wear", "nakydky-ta-obladunky"), ("minidoll", "chastyny-minilialok"),
    ("baseplate", "bazovi-plastyny"), ("duplo", "duplo"), ("sticker", "nalipky"),
    ("technic, liftarm", "balky-technic"), ("technic, axle", "osi-technic"), ("technic, pin", "shtyfty-technic"),
    ("technic, bush", "vtulky-technic"), ("technic, connector", "zjednuvachi-technic"), ("technic, gear", "shesterni"),
    ("technic, panel", "paneli-technic"), ("technic, brick", "tsehlynky-technic"), ("technic", "spetsialni-elementy-technic"),
    ("slope, curved", "arky-ta-vyhnuti-tsehlynky"), ("arch", "arky-ta-vyhnuti-tsehlynky"), ("slope", "skosy"),
    ("wedge, plate", "klynopodibni-plastyny"), ("wedge", "klynopodibni-tsehlynky"),
    ("brick, round", "kruhli-tsehlynky-ta-konusy"), ("cone", "kruhli-tsehlynky-ta-konusy"),
    ("brick, modified", "modyfikovani-tsehlynky"), ("brick", "zvychaini-tsehlynky"),
    ("plate, round", "kruhli-plastyny-ta-tarilky"), ("dish", "kruhli-plastyny-ta-tarilky"),
    ("plate, modified", "modyfikovani-plastyny"), ("bracket", "modyfikovani-plastyny"), ("plate", "zvychaini-plastyny"),
    ("tile, round", "kruhli-ta-vyhnuti-plytky"), ("tile, modified", "modyfikovani-plytky"), ("tile", "zvychaini-plytky"),
    ("wheel", "kolesa-ta-shyny"), ("tire", "kolesa-ta-shyny"), ("windscreen", "lobove-sklo-ta-fiuzeliazh"),
    ("window", "ramy-vikna-ta-dveri"), ("door", "ramy-vikna-ta-dveri"), ("glass", "ramy-vikna-ta-dveri"),
    ("hinge", "sharniry-ta-povorotni-platformy"), ("turntable", "sharniry-ta-povorotni-platformy"),
    ("panel", "paneli"), ("fence", "ohorozhi-ta-drabyny"), ("ladder", "ohorozhi-ta-drabyny"), ("bar", "ohorozhi-ta-drabyny"),
    ("support", "opory-balky-ta-krany"), ("container", "kontejnery-ta-yashchyky"), ("flag", "prapory-ta-znaky"),
    ("sign", "prapory-ta-znaky"), ("plant", "roslyny"), ("animal", "tvaryny-ta-istoty"), ("hose", "trubky-ta-shlanhy"),
    ("string", "nytky-humky-ta-kotushky"), ("rock", "kaminnia-ta-skeli"), ("magnet", "mahnity-ta-trymachi"),
    ("vehicle", "dlia-transportu"), ("boat", "korpusy-chovniv-i-litakiv"), ("aircraft", "korpusy-chovniv-i-litakiv"),
    ("wing", "klynopodibni-plastyny"), ("electric", "elektronika"), ("bionicle", "bionicle"),
]


def _section(*texts: str) -> Category | None:
    """The shop section for BrickLink's category, or failing that for the part name."""
    for text in texts:
        low = (text or "").lower()
        for needle, slug in SECTION_RULES:
            if low and needle in low:
                cat = Category.objects.filter(slug=slug).first()
                if cat:
                    return cat
    return None


def bricklink_title(kind: str, number: str) -> dict | None:
    """{"name", "category"} from BrickLink's catalogue page, or None when unavailable. Cached."""
    key = f"bricklink:title:{kind}:{number.lower()}"
    found = cache.get(key)
    if found is not None:
        return found or None
    if cache.get(OFFLINE_KEY):
        return None
    url = CATALOG_PAGE.format(urllib.parse.urlencode({kind: number}))
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; BrickHub-shop/1.0)",
                                                   "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            page = response.read(200_000).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        logger.info("BrickLink is not reachable from this server: %s", e)
        cache.set(OFFLINE_KEY, True, 600)  # do not keep waiting on every lookup
        return None
    match = TITLE_RE.search(page)
    if not match:
        cache.set(key, {}, 3600)
        return None
    rest = html.unescape(match.group("rest")).strip()
    rest = re.sub(r"^LEGO\s+", "", rest)
    category = ""
    cat = re.search(r"\[([^\[\]]+)\]\s*$", rest)
    if cat:
        category, rest = cat.group(1).strip(), rest[:cat.start()].strip()
    info = {"name": rest[:255], "category": category}
    cache.set(key, info, 60 * 60 * 24 * 30)
    return info


def known_part(number: str) -> Part | None:
    """The catalogue part for a number as the owner types it: the shop's Design ID, the BrickLink number or
    LEGO's own design number (when it points to one part only)."""
    number = (number or "").strip()
    if not number:
        return None
    part = (Part.objects.filter(design_id__iexact=number).select_related("category").first()
            or Part.objects.filter(bricklink_no__iexact=number).select_related("category").first())
    if part:
        return part
    same_lego = list(Part.objects.filter(lego_no__iexact=number).select_related("category")[:2])
    if len(same_lego) == 1:  # many printed torsos share LEGO's 76382: that number alone does not name one
        return same_lego[0]
    # one LEGO design number can cover several catalogue parts (moulds, prints); the part with clearly the most
    # elements is the plain one (48183 -> 48183, not 4859); a generic torso design matches none
    counts = list(Element.objects.filter(lego_design_id=number).order_by().values("part_id")
                  .annotate(n=Count("id")).order_by("-n")[:2])
    if counts and (len(counts) == 1 or counts[0]["n"] >= 2 * counts[1]["n"]):
        return Part.objects.select_related("category").get(pk=counts[0]["part_id"])
    return None


def element_for(part: Part, color_id) -> str:
    """The newest Element ID of a part in a colour, or ''."""
    return lego_numbers(part, color_id)[0]


def lego_numbers(part: Part, color_id=None) -> tuple[str, str]:
    """(Element ID, LEGO design number) of a part in a colour as lego.com has them; ('', part's LEGO number)."""
    if not part or not part.pk:
        return "", ""
    row = None
    if color_id:
        row = (Element.objects.filter(part=part, color_id=color_id).order_by("-element_id")
               .values_list("element_id", "lego_design_id").first())
    return (row[0] if row else ""), ((row[1] if row else "") or part.lego_no)


def base_part(number: str) -> Part | None:
    """The plain mould of a printed / assembled number from the local catalogue: 973pb1234c01 → 973."""
    # only where letters follow (973pb..., 3626bpr...): a plain number such as 76382 is not 763 + something
    candidates = [number[:i] for i in range(len(number) - 1, 2, -1) if number[i].isalpha()]
    found = {p.design_id.lower(): p for p in Part.objects.filter(design_id__in=candidates).select_related("category")}
    for candidate in candidates:
        if candidate.lower() in found:
            return found[candidate.lower()]
    return None


class LookupBudget:
    """At most `limit` BrickLink requests per bulk import, so a big file does not wait on hundreds of pages."""

    def __init__(self, limit: int = 40):
        self.left = limit

    def take(self) -> bool:
        self.left -= 1
        return self.left >= 0


def family_section(number: str) -> tuple[Category, str] | tuple[None, None]:
    """The section shared by catalogue parts whose number starts the same way: 973pb1234c01 -> 973... -> torsos.

    The longest such start wins, and only when nearly all those parts (80%+) are in one section."""
    for i in range(len(number) - 1, 2, -1):
        if not number[i].isalpha():
            continue
        prefix = number[:i]
        rows = list(Part.objects.filter(design_id__istartswith=prefix).exclude(category=None).order_by()
                    .values("category").annotate(n=Count("id")).order_by("-n")[:5])
        total = sum(r["n"] for r in rows)
        if total >= 3 and rows[0]["n"] >= 0.8 * total:
            return Category.objects.get(pk=rows[0]["category"]), prefix
    return None, None


def new_part_info(number: str, online: bool = True) -> dict:
    """{"name", "category", "source"} for a part number that is not in the local catalogue."""
    online = bricklink_title("P", number) if online else cache.get(f"bricklink:title:P:{number.lower()}")
    base = base_part(number)
    if online and online.get("name"):
        category = (_section(online.get("category", ""), online["name"]) or (base.category if base else None)
                    or family_section(number)[0])
        return {"name": online["name"], "category": category, "source": "bricklink"}
    if base is not None:
        return {"name": f"{base.name} ({number})", "category": base.category, "source": "base", "base": base.design_id}
    category, prefix = family_section(number)
    if category is not None:
        return {"name": f"{category.name} ({number})", "category": category, "source": "base", "base": f"{prefix}…"}
    # a LEGO design number shared by many catalogue parts (a printed torso design): their common section
    cats = Counter(Part.objects.filter(elements__lego_design_id=number).exclude(category=None)
                   .values_list("category", flat=True))
    if cats:
        category = Category.objects.get(pk=cats.most_common(1)[0][0])
        return {"name": f"{category.name} ({number})", "category": category, "source": "design"}
    return {"name": number, "category": None, "source": "none"}


def new_minifig_info(number: str, online: bool = True) -> dict:
    """{"name", "theme", "source"} for a BrickLink minifigure number that is not in the local catalogue."""
    online = bricklink_title("M", number) if online else cache.get(f"bricklink:title:M:{number.lower()}")
    if online and online.get("name"):
        theme = None
        first = online.get("category", "").split(":")[0].strip()
        if first:
            theme = (Theme.objects.filter(title__iexact=f"LEGO {first}").first()
                     or Theme.objects.filter(name__iexact=first, parent__isnull=True).first())
        return {"name": online["name"], "theme": theme, "source": "bricklink"}
    return {"name": number, "theme": None, "source": "none"}
