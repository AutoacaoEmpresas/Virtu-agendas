"""Registro do histórico de agendas (LogAgenda).

Cada ação salva gera UMA linha: tira-se um "retrato" (snapshot) da agenda antes e depois
de salvar e grava-se só a diferença entre eles.
"""

from .models import Agenda, LogAgenda

STATUS_AGENDA_LABELS = {"confirmado": "Confirmada", "cancelado": "Cancelada", "esperando": "Esperando"}
DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def carregar(agenda_id):
    """Busca a agenda direto do banco (evita valores em memória ainda não normalizados)."""
    return Agenda.objects.select_related("horario", "medico_inicial", "medico_atendido").get(pk=agenda_id)


def resumo(agenda):
    h = agenda.horario
    sala = agenda.sala
    local = f"{sala.nome} ({sala.unidade.nome})" if sala else "Sem sala"
    return f"{h.data:%d/%m/%Y} · {h.horario_inicio:%H:%M}–{h.horario_fim:%H:%M} · {local}"


def snapshot(agenda):
    """Campos legíveis da agenda, na ordem em que aparecem no histórico."""
    h = agenda.horario
    sala = agenda.sala
    cancelado = agenda.status_medico_inicial == Agenda.StatusMedicoInicial.CANCELADO
    substituto = agenda.medico_atendido if cancelado and agenda.medico_atendido_id else None
    procedimentos = "; ".join(
        f"{pa.procedimento.nome_procedimento} (previsto {pa.esperanca_pacientes}, "
        f"real {'-' if pa.real_pacientes is None else pa.real_pacientes})"
        for pa in agenda.procedimentoagenda_set.select_related("procedimento").order_by("id")
    )
    return {
        "Data": f"{h.data:%d/%m/%Y}",
        "Horário": f"{h.horario_inicio:%H:%M}–{h.horario_fim:%H:%M}",
        "Unidade": sala.unidade.nome if sala else "-",
        "Sala": sala.nome if sala else "-",
        "Médico inicial": agenda.medico_inicial.nome if agenda.medico_inicial_id else "-",
        "Status do médico inicial": agenda.get_status_medico_inicial_display(),
        "Médico substituto": substituto.nome if substituto else "-",
        "Substituto confirmado": ("Sim" if agenda.confirmacao_medico else "Não") if substituto else "-",
        "Status da agenda": STATUS_AGENDA_LABELS[agenda.status],
        "Concierge": agenda.concierge or "-",
        "Realizada": "Sim" if agenda.realizada else "Não",
        "Chegada do médico": f"{agenda.hora_chegada:%H:%M}" if agenda.hora_chegada else "-",
        "Saída do médico": f"{agenda.hora_saida:%H:%M}" if agenda.hora_saida else "-",
        "Procedimentos": procedimentos or "-",
    }


def diferencas(antes, depois):
    return [
        {"campo": campo, "antes": antes.get(campo, ""), "depois": valor}
        for campo, valor in depois.items()
        if antes.get(campo, "") != valor
    ]


def como_cadastro(retrato):
    return [{"campo": c, "antes": "", "depois": v} for c, v in retrato.items()]


def como_exclusao(retrato):
    return [{"campo": c, "antes": v, "depois": ""} for c, v in retrato.items()]


def lista_datas(agendas):
    return ", ".join(f"#{a.id} ({a.horario.data:%d/%m/%Y})" for a in agendas)


def descrever_recorrencia(recorrencia):
    intervalo = "toda semana" if recorrencia.intervalo_semanas == 1 else "a cada 15 dias"
    return (
        f"{DIAS_SEMANA[recorrencia.dia_semana]}, {intervalo}, "
        f"de {recorrencia.data_inicial:%d/%m/%Y} a {recorrencia.data_final:%d/%m/%Y}"
    )


def registrar(usuario, acao, agenda, alteracoes, resumo_texto=None):
    if not alteracoes:
        return None
    return LogAgenda.objects.create(
        usuario=usuario,
        usuario_nome=usuario.get_full_name() or usuario.username,
        usuario_cargo=usuario.get_cargo_display(),
        acao=acao,
        agenda_numero=agenda.id,
        unidade=agenda.unidade,
        resumo=resumo_texto or resumo(agenda),
        alteracoes=alteracoes,
    )
