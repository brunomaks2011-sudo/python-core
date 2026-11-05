from django.contrib.sitemaps.views import sitemap
from django.urls import path

from . import views
from .sitemaps import SITEMAPS

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("dostavka-i-oplata/", views.page, {"key": "delivery"}, name="delivery"),
    path("pro-nas/", views.page, {"key": "about"}, name="about"),
    path("kontakty/", views.page, {"key": "contacts"}, name="contacts"),
    path("obmin-i-povernennia/", views.page, {"key": "returns"}, name="returns"),
    path("umovy/", views.page, {"key": "terms"}, name="terms"),
    path("konfidentsiinist/", views.page, {"key": "privacy"}, name="privacy"),
    path("yak-znaity-detal/", views.page, {"key": "guide"}, name="guide"),
    path("robots.txt", views.robots_txt, name="robots"),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
]
