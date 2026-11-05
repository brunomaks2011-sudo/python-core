"""Structured data (schema.org JSON-LD) helpers."""
from django.conf import settings


def product_jsonld(request, product, image_url: str) -> dict:
    image = request.build_absolute_uri(image_url) if image_url.startswith("/") else image_url
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.title,
        "sku": product.sku,
        "image": [image],
        "description": (product.description or product.title)[:500],
        "brand": {"@type": "Brand", "name": "LEGO"},
        "offers": {
            "@type": "Offer",
            "url": request.build_absolute_uri(product.get_absolute_url()),
            "priceCurrency": "UAH",
            "price": f"{product.price:.2f}",
            "availability": "https://schema.org/InStock" if product.in_stock else "https://schema.org/OutOfStock",
            "itemCondition": "https://schema.org/NewCondition" if product.condition == "new"
            else "https://schema.org/UsedCondition",
            "seller": {"@type": "Organization", "name": settings.SHOP["NAME"]},
        },
    }
    if product.official_number:
        data["mpn"] = product.official_number
    if product.reviews_count:
        data["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": f"{product.rating_avg:.1f}",
                                   "reviewCount": product.reviews_count}
    return data


def breadcrumbs_jsonld(request, crumbs) -> dict:
    items = []
    for pos, (name, url) in enumerate([("Головна", "/")] + list(crumbs), start=1):
        item = {"@type": "ListItem", "position": pos, "name": name}
        if url:
            item["item"] = request.build_absolute_uri(url)
        items.append(item)
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}


def organization_jsonld(request) -> dict:
    shop = settings.SHOP
    data = {"@context": "https://schema.org", "@type": "Store", "name": shop["NAME"],
            "url": request.build_absolute_uri("/"), "currenciesAccepted": "UAH", "areaServed": "UA"}
    if shop["PHONE"]:
        data["telephone"] = shop["PHONE"]
    if shop["EMAIL"]:
        data["email"] = shop["EMAIL"]
    return data
