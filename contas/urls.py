from django.urls import path

from . import views

app_name = "contas"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("login/otp/", views.verificar_otp_view, name="verificar_otp"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
]
