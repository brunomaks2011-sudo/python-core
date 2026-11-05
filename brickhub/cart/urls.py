from django.urls import path

from . import views

app_name = "cart"

urlpatterns = [
    path("", views.cart_detail, name="detail"),
    path("dodaty/", views.add, name="add"),
    path("onovyty/<int:item_id>/", views.update, name="update"),
    path("vydalyty/<int:item_id>/", views.remove, name="remove"),
    path("ochystyty/", views.clear, name="clear"),
    path("promokod/", views.promo, name="promo"),
    path("shvydke-zamovlennia/", views.quick_order, name="quick_order"),
]
