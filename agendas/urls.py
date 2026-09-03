from django.urls import path

from . import views

app_name = "agendas"

urlpatterns = [
    path("", views.home, name="home"),
    path("dia/<str:data>/agendamentos/", views.lista_agendamentos, name="lista_agendamentos"),
    path("agenda/nova/", views.cadastro_agenda, name="cadastro_agenda_nova"),
    path("agenda/<int:agenda_id>/editar/", views.cadastro_agenda, name="cadastro_agenda_editar"),
]
