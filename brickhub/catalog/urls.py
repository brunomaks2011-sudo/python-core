from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("katalog/", views.catalog_index, name="index"),
    path("katalog/<slug:slug>/", views.category_detail, name="category"),
    path("serii/<slug:slug>/", views.theme_detail, name="theme"),
    path("kolektsiia/<slug:slug>/", views.collection_detail, name="collection"),
    path("tovar/<slug:slug>/", views.product_detail, name="product"),
    path("poshuk/", views.search, name="search"),
    path("api/poshuk/", views.suggest, name="suggest"),
    path("detali/", views.part_finder, name="part_finder"),
    path("detali/<str:design_id>/", views.part_design, name="part_design"),
    path("kolory/", views.colors_index, name="colors"),
    path("kolory/<slug:slug>/", views.color_detail, name="color"),
    path("obrane/", views.favorites, name="favorites"),
    path("obrane/<int:pk>/", views.toggle_favorite, name="toggle_favorite"),
    path("porivniannia/", views.compare, name="compare"),
    path("porivniannia/<int:pk>/", views.toggle_compare, name="toggle_compare"),
    path("tovar/<int:pk>/vidguk/", views.review_create, name="review_create"),
    path("tovar/<int:pk>/povidomyty/", views.stock_notify, name="stock_notify"),
    path("img/part/<str:design_id>/<int:color_id>.svg", views.part_svg, name="part_svg"),
    path("img/fig/<str:accent>.svg", views.fig_svg, name="fig_svg"),
]
