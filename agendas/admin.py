from django.contrib import admin

from .models import (
    Agenda,
    ContaBancaria,
    Horario,
    Medico,
    Procedimento,
    ProcedimentoAgenda,
    Sala,
    SalaHorario,
    Unidade,
    UnidadeMedico,
)

admin.site.register(Unidade)
admin.site.register(Sala)
admin.site.register(ContaBancaria)
admin.site.register(Medico)
admin.site.register(UnidadeMedico)
admin.site.register(Procedimento)
admin.site.register(Horario)
admin.site.register(SalaHorario)
admin.site.register(Agenda)
admin.site.register(ProcedimentoAgenda)
