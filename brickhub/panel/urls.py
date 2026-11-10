from django.urls import path

from . import views

app_name = "panel"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("tovary/", views.product_list, name="products"),
    path("tovary/novyi/", views.product_edit, name="product_new"),
    path("tovary/masovo/", views.product_bulk, name="product_bulk"),
    path("tovary/<int:pk>/", views.product_edit, name="product_edit"),
    path("tovary/<int:pk>/shvydko/", views.product_quick_update, name="product_quick_update"),
    path("tovary/<int:pk>/vydalyty/", views.product_delete, name="product_delete"),
    path("foto/<int:pk>/", views.image_action, name="image_action"),
    path("foto/prybraty-fon/", views.photos_remove_backgrounds, name="photos_remove_backgrounds"),
    path("api/katalog/", views.catalog_lookup, name="catalog_lookup"),
    path("zamovlennia/", views.order_list, name="orders"),
    path("zamovlennia/<int:pk>/", views.order_detail, name="order_detail"),
    path("zamovlennia/<int:pk>/pakuvannia/", views.order_packing, name="order_packing"),
    path("korystuvachi/", views.user_list, name="users"),
    path("korystuvachi/<int:pk>/", views.user_detail, name="user_detail"),
    path("vidguky/", views.review_list, name="reviews"),
    path("povidomlennia/", views.notification_list, name="notifications"),
    path("import/", views.import_view, name="import"),
    path("import/shablon/<str:kind>.xlsx", views.import_template, name="import_template"),
    path("eksport/tovary.csv", views.export_products, name="export_products"),
    path("dovidnyk/<str:key>/", views.crud_list, name="crud_list"),
    path("dovidnyk/<str:key>/novyi/", views.crud_edit, name="crud_new"),
    path("dovidnyk/<str:key>/<int:pk>/", views.crud_edit, name="crud_edit"),
    path("dovidnyk/<str:key>/<int:pk>/vydalyty/", views.crud_delete, name="crud_delete"),
]
