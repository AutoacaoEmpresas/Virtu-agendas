from django.contrib import admin

from .models import (
    Agenda,
    ContaBancaria,
    FechamentoRepasse,
    Horario,
    ItemRepasse,
    LogAgenda,
    Medico,
    Procedimento,
    ProcedimentoAgenda,
    Recorrencia,
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
admin.site.register(Recorrencia)


@admin.register(LogAgenda)
class LogAgendaAdmin(admin.ModelAdmin):
    list_display = ("criado_em", "usuario_nome", "acao", "agenda_numero", "resumo")
    list_filter = ("acao", "unidade")
    search_fields = ("usuario_nome", "resumo", "agenda_numero")

    # Histórico é somente leitura, inclusive no /admin/.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ItemRepasseInline(admin.TabularInline):
    model = ItemRepasse
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in ItemRepasse._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(FechamentoRepasse)
class FechamentoRepasseAdmin(admin.ModelAdmin):
    list_display = ("competencia", "medico", "status", "valor_total", "pago_em")
    list_filter = ("status", "competencia")
    search_fields = ("medico__nome",)
    inlines = [ItemRepasseInline]
