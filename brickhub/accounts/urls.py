from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("vkhid/", views.login_view, name="login"),
    path("vykhid/", views.logout_view, name="logout"),
    path("reiestratsiia/", views.register, name="register"),
    path("profil/", views.profile, name="profile"),
    path("parol/", views.password_change, name="password_change"),
    path("zamovlennia/", views.orders, name="orders"),
    path("zamovlennia/<str:number>/", views.order_detail, name="order_detail"),
    path("zamovlennia/<str:number>/povtoryty/", views.order_repeat, name="order_repeat"),
    path("zamovlennia/<str:number>/skasuvaty/", views.order_cancel, name="order_cancel"),
    path("povidomlennia/", views.notifications, name="notifications"),
    path("povidomlennia/<int:pk>/vydalyty/", views.notification_delete, name="notification_delete"),
    path("vidnovlennia-parolia/", views.PasswordResetView.as_view(), name="password_reset"),
    path("vidnovlennia-parolia/nadislano/", views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("vidnovlennia-parolia/<uidb64>/<token>/", views.PasswordResetConfirmView.as_view(),
         name="password_reset_confirm"),
    path("vidnovlennia-parolia/gotovo/", views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
]
