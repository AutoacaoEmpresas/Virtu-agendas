from django.urls import path

from . import views

app_name = "agendas"

urlpatterns = [
    path("", views.home, name="home"),
    path("dia/<str:data>/agendamentos/", views.lista_agendamentos, name="lista_agendamentos"),
    path("agenda/nova/", views.cadastro_agenda, name="cadastro_agenda_nova"),
    path("agenda/<int:agenda_id>/editar/", views.cadastro_agenda, name="cadastro_agenda_editar"),
    path("agenda/<int:agenda_id>/excluir/", views.excluir_agenda, name="agenda_excluir"),
    path("medicos/", views.medicos_lista, name="medicos_lista"),
    path("medicos/novo/", views.medico_form, name="medico_novo"),
    path("medicos/<int:medico_id>/editar/", views.medico_form, name="medico_editar"),
    path("medicos/<int:medico_id>/excluir/", views.medico_excluir, name="medico_excluir"),
]
