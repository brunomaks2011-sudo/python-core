"""Product search: LEGO set numbers, Design IDs, Element IDs, minifigure numbers,
colours, series and free text (Ukrainian or English)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.core.cache import cache
from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Value, When

from .models import Color, Element, LegoSet, Minifigure, Part

TOKEN_RE = re.compile(r"[\s,;/]+")
NUMBER_RE = re.compile(r"^[a-z]{0,4}\d{2,8}[a-z]{0,3}(?:pr\d+)?(?:-\d+)?$", re.I)


def _color_index() -> list[tuple[str, int]]:
    """(lowercase name, colour id), longest names first."""
    idx = cache.get("search:colors")
    if idx is None:
        idx = []
        for c in Color.objects.filter(is_active=True).only("id", "name", "name_uk", "lego_name"):
            for n in (c.name, c.name_uk, c.lego_name):
                if n:
                    idx.append((n.lower(), c.pk))
        idx.sort(key=lambda t: -len(t[0]))
        cache.set("search:colors", idx, 600)
    return idx


@dataclass
class ParsedQuery:
    raw: str
    text_tokens: list = field(default_factory=list)
    color_ids: list = field(default_factory=list)
    color_names: list = field(default_factory=list)
    numbers: list = field(default_factory=list)


def parse(q: str) -> ParsedQuery:
    raw = (q or "").strip()
    parsed = ParsedQuery(raw=raw)
    text = " " + raw.lower() + " "
    # colours: match whole phrases ("темно-сірий блакитнуватий", "light bluish gray")
    for name, cid in _color_index():
        if len(name) < 3:
            continue
        pattern = f" {name} "
        if pattern in text:
            if cid not in parsed.color_ids:
                parsed.color_ids.append(cid)
                parsed.color_names.append(name)
            text = text.replace(pattern, " ")
    tokens = [t for t in TOKEN_RE.split(text.strip()) if t]
    for tok in tokens:
        if NUMBER_RE.match(tok) and any(ch.isdigit() for ch in tok):
            parsed.numbers.append(tok)
        parsed.text_tokens.append(tok)
    return parsed


def search_products(qs, q: str):
    """Filter ``qs`` by the query. Returns (queryset annotated with ``rank``, ParsedQuery)."""
    parsed = parse(q)
    if not parsed.raw:
        return qs, parsed
    for tok in parsed.text_tokens:
        qs = qs.filter(search_text__icontains=tok)
    if parsed.color_ids:
        qs = qs.filter(color_id__in=parsed.color_ids)
    whens = []
    for num in parsed.numbers:
        base = num.split("-")[0]
        whens += [
            When(part__design_id__iexact=num, then=Value(100)),
            When(lego_set__number__iexact=num if "-" in num else f"{num}-1", then=Value(100)),
            When(minifigure__fig_number__iexact=num, then=Value(100)),
            When(minifigure__bricklink_id__iexact=num, then=Value(100)),
            When(sku__iexact=num, then=Value(100)),
            When(Exists(Element.objects.filter(part_id=OuterRef("part_id"), color_id=OuterRef("color_id"),
                                               element_id=num)), then=Value(90)),
            When(lego_set__number__istartswith=f"{base}-", then=Value(60)),
            When(part__design_id__istartswith=num, then=Value(40)),
        ]
    if parsed.text_tokens:
        first = " ".join(t for t in parsed.text_tokens if t not in parsed.numbers)
        if first:
            whens.append(When(title__istartswith=first, then=Value(30)))
    rank = Case(*whens, default=Value(0), output_field=IntegerField()) if whens else Value(0)
    return qs.annotate(rank=rank), parsed


def catalog_matches(parsed: ParsedQuery, limit: int = 6) -> list[dict]:
    """Official catalogue entries (not necessarily on sale) matching a number."""
    out = []
    for num in parsed.numbers[:3]:
        set_num = num if "-" in num else f"{num}-1"
        for s in LegoSet.objects.filter(number__iexact=set_num).select_related("theme")[:1]:
            out.append({"kind": "set", "number": s.base_number, "name": s.name, "year": s.year,
                        "extra": f"{s.pieces} дет." if s.pieces else "", "image": s.image_url,
                        "theme": s.theme.display_name if s.theme else ""})
        for p in Part.objects.filter(Q(design_id__iexact=num) | Q(elements__element_id=num)).distinct()[:2]:
            out.append({"kind": "part", "number": p.design_id, "name": p.display_name, "official": p.name,
                        "year": None, "extra": "", "image": "", "theme": ""})
        for m in Minifigure.objects.filter(Q(fig_number__iexact=num) | Q(bricklink_id__iexact=num))[:1]:
            out.append({"kind": "minifig", "number": m.display_number, "name": m.name, "year": m.year,
                        "extra": "", "image": m.image_url, "theme": ""})
    return out[:limit]
