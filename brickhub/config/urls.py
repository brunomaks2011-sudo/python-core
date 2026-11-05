from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from orders.urls import api_urlpatterns as orders_api

admin.site.site_header = "BRICK HUB — системна адмінка"
admin.site.site_title = "BRICK HUB"

urlpatterns = [
    path("", include("core.urls")),
    path("", include("catalog.urls")),
    path("koshyk/", include("cart.urls")),
    path("zamovlennia/", include("orders.urls")),
    path("", include((orders_api, "orders_api"))),
    path("kabinet/", include("accounts.urls")),
    path("panel/", include("panel.urls")),
    path("django-admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = "core.views.error_404"
handler500 = "core.views.error_500"
