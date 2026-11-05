from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("oformlennia/", views.checkout, name="checkout"),
    path("vidstezhennia/", views.track, name="track"),
    path("liqpay/callback/", views.liqpay_callback, name="liqpay_callback"),
    path("<str:number>/", views.success, name="success"),
    path("<str:number>/oplata/", views.pay, name="pay"),
]

api_urlpatterns = [
    path("api/np/mista/", views.np_cities, name="np_cities"),
    path("api/np/viddilennia/", views.np_warehouses, name="np_warehouses"),
]
