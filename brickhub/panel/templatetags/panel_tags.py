from django import template
from django.utils.html import format_html

from panel.owners import owner_people

register = template.Library()


def _people(context) -> dict:
    cache = context.render_context
    if "_owner_people" not in cache:
        cache["_owner_people"] = {p["pk"]: p for p in owner_people()}
    return cache["_owner_people"]


@register.simple_tag(takes_context=True)
def owner_badge(context, owner_id):
    """Coloured label with the name of whose goods a listing is."""
    person = _people(context).get(owner_id)
    if person is None:
        return format_html('<span class="owner is-none" title="{}">{}</span>', "Власника не вказано", "не вказано")
    return format_html('<span class="owner" style="--c:{}" title="{} · {}">{}</span>', person["color"],
                       person["role"], person["email"], person["name"])
