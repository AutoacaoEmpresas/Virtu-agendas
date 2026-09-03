import calendar
import datetime
from collections import defaultdict

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .models import (
    Agenda,
    Horario,
    Medico,
    Procedimento,
    ProcedimentoAgenda,
    Sala,
    SalaHorario,
    Unidade,
)

DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

# Paleta simples para colorir eventos por unidade (ciclo).
CORES_UNIDADE = [
    "#4C6EF5", "#12B886", "#F59F00", "#E64980", "#7048E8", "#15AABF", "#FA5252",
]


def _cor_unidade(unidade_id):
    if unidade_id is None:
        return "#868E96"
    return CORES_UNIDADE[unidade_id % len(CORES_UNIDADE)]


def _parse_date(value, default):
    if not value:
        return default
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return default


def _monday(date):
    return date - datetime.timedelta(days=date.weekday())


def home(request):
    hoje = datetime.date.today()
    semana_ref = _parse_date(request.GET.get("semana"), hoje)
    inicio_semana = _monday(semana_ref)
    fim_semana = inicio_semana + datetime.timedelta(days=6)

    busca = request.GET.get("q", "").strip()
    unidade_filtro = request.GET.get("unidade", "").strip()

    agendas_qs = (
        Agenda.objects.select_related("horario", "medico_inicial", "medico_atendido")
        .prefetch_related("horario__salas__unidade")
        .filter(horario__data__range=[inicio_semana, fim_semana])
    )

    if unidade_filtro:
        agendas_qs = agendas_qs.filter(horario__salas__unidade_id=unidade_filtro)

    if busca:
        agendas_qs = agendas_qs.filter(
            Q(medico_inicial__nome__icontains=busca)
            | Q(medico_atendido__nome__icontains=busca)
            | Q(horario__salas__nome__icontains=busca)
            | Q(horario__salas__especialidade__icontains=busca)
            | Q(horario__salas__unidade__nome__icontains=busca)
        )

    agendas_qs = agendas_qs.distinct().order_by("horario__data", "horario__horario_inicio")

    dias_semana = []
    for i in range(7):
        dia = inicio_semana + datetime.timedelta(days=i)
        eventos = []
        for ag in agendas_qs:
            if ag.horario.data != dia:
                continue
            sala = ag.sala
            eventos.append(
                {
                    "agenda": ag,
                    "sala": sala,
                    "unidade": sala.unidade if sala else None,
                    "cor": _cor_unidade(sala.unidade_id if sala else None),
                    "tem_medico": ag.medico_inicial_id is not None,
                }
            )
        dias_semana.append({"data": dia, "nome": DIAS_SEMANA[i], "eventos": eventos})

    # Mini-calendário do mês da semana selecionada.
    mes_ref = inicio_semana.replace(day=1)
    cal = calendar.Calendar(firstweekday=0)
    semanas_mes = cal.monthdatescalendar(mes_ref.year, mes_ref.month)
    primeiro_dia_mes = mes_ref
    if mes_ref.month == 12:
        ultimo_dia_mes = mes_ref.replace(day=31)
    else:
        ultimo_dia_mes = mes_ref.replace(month=mes_ref.month + 1, day=1) - datetime.timedelta(days=1)

    dias_com_agenda = set(
        Horario.objects.filter(
            data__range=[semanas_mes[0][0], semanas_mes[-1][-1]]
        ).values_list("data", flat=True)
    )

    # Lista lateral de agendas abertas (sem médico alocado) do mês corrente.
    abertas_qs = (
        Agenda.objects.select_related("horario")
        .prefetch_related("horario__salas__unidade")
        .filter(
            medico_inicial__isnull=True,
            horario__data__range=[primeiro_dia_mes, ultimo_dia_mes],
        )
        .order_by("horario__data", "horario__horario_inicio")
    )
    agendas_abertas_por_dia = defaultdict(list)
    for ag in abertas_qs:
        sala = ag.sala
        agendas_abertas_por_dia[ag.horario.data].append(
            {
                "agenda": ag,
                "unidade": sala.unidade if sala else None,
                "especialidade": sala.especialidade if sala else "",
                "turno": ag.horario.turno,
            }
        )

    context = {
        "inicio_semana": inicio_semana,
        "fim_semana": fim_semana,
        "semana_anterior": (inicio_semana - datetime.timedelta(days=7)).isoformat(),
        "semana_proxima": (inicio_semana + datetime.timedelta(days=7)).isoformat(),
        "dias_semana": dias_semana,
        "unidades": Unidade.objects.all(),
        "busca": busca,
        "unidade_filtro": unidade_filtro,
        "mes_ref": mes_ref,
        "semanas_mes": semanas_mes,
        "dias_com_agenda": dias_com_agenda,
        "hoje": hoje,
        "agendas_abertas_por_dia": sorted(agendas_abertas_por_dia.items()),
    }
    return render(request, "agendas/home.html", context)


def lista_agendamentos(request, data):
    dia = _parse_date(data, datetime.date.today())
    busca = request.GET.get("q", "").strip()
    ordenar = request.GET.get("ordenar", "recentes")

    agendas_qs = (
        Agenda.objects.select_related("horario", "medico_inicial", "medico_atendido")
        .prefetch_related("horario__salas__unidade", "procedimentoagenda_set__procedimento")
        .filter(horario__data=dia)
    )

    if busca:
        agendas_qs = agendas_qs.filter(
            Q(medico_inicial__nome__icontains=busca)
            | Q(medico_atendido__nome__icontains=busca)
            | Q(procedimentoagenda_set__procedimento__nome_procedimento__icontains=busca)
            | Q(horario__salas__unidade__nome__icontains=busca)
        ).distinct()

    if ordenar == "antigos":
        agendas_qs = agendas_qs.order_by("horario__horario_inicio")
    else:
        agendas_qs = agendas_qs.order_by("-horario__horario_inicio")

    linhas = []
    for ag in agendas_qs:
        sala = ag.sala
        procedimentos = list(ag.procedimentoagenda_set.select_related("procedimento"))
        linhas.append(
            {
                "agenda": ag,
                "sala": sala,
                "unidade": sala.unidade if sala else None,
                "procedimentos": procedimentos,
                "pacientes_esperados": sum(p.esperanca_pacientes for p in procedimentos) if procedimentos else 0,
            }
        )

    context = {
        "dia": dia,
        "linhas": linhas,
        "busca": busca,
        "ordenar": ordenar,
    }
    return render(request, "agendas/partials/_lista_agendamentos.html", context)


def cadastro_agenda(request, agenda_id=None):
    agenda = None
    if agenda_id:
        agenda = get_object_or_404(
            Agenda.objects.select_related("horario", "medico_inicial", "medico_atendido").prefetch_related(
                "horario__salas__unidade", "procedimentoagenda_set__procedimento"
            ),
            pk=agenda_id,
        )

    if request.method == "POST":
        return _salvar_agenda(request, agenda)

    horario_pref_id = request.GET.get("horario")
    unidade_pref_id = request.GET.get("unidade")
    sala_pref = None
    data_pref = None
    horario_inicio_pref = None
    horario_fim_pref = None

    if agenda:
        sala_pref = agenda.sala
        unidade_pref_id = sala_pref.unidade_id if sala_pref else unidade_pref_id
        data_pref = agenda.horario.data
        horario_inicio_pref = agenda.horario.horario_inicio
        horario_fim_pref = agenda.horario.horario_fim
    elif horario_pref_id:
        try:
            horario_ref = Horario.objects.prefetch_related("salas__unidade").get(pk=horario_pref_id)
            sala_pref = horario_ref.salas.first()
            unidade_pref_id = sala_pref.unidade_id if sala_pref else unidade_pref_id
            data_pref = horario_ref.data
            horario_inicio_pref = horario_ref.horario_inicio
            horario_fim_pref = horario_ref.horario_fim
        except Horario.DoesNotExist:
            pass

    procedimentos_agenda = []
    if agenda:
        procedimentos_agenda = list(agenda.procedimentoagenda_set.select_related("procedimento"))

    context = {
        "agenda": agenda,
        "unidades": Unidade.objects.all(),
        "salas": Sala.objects.select_related("unidade").all(),
        "medicos": Medico.objects.all(),
        "procedimentos": Procedimento.objects.select_related("unidade").all(),
        "unidade_pref_id": str(unidade_pref_id) if unidade_pref_id else "",
        "sala_pref": sala_pref,
        "data_pref": data_pref,
        "horario_inicio_pref": horario_inicio_pref,
        "horario_fim_pref": horario_fim_pref,
        "procedimentos_agenda": procedimentos_agenda,
    }
    return render(request, "agendas/partials/_cadastro_agenda.html", context)


@transaction.atomic
def _salvar_agenda(request, agenda):
    post = request.POST

    sala_id = post.get("sala")
    sala = get_object_or_404(Sala, pk=sala_id) if sala_id else None

    medico_inicial_id = post.get("medico_inicial") or None
    medico_inicial_status = post.get("medico_inicial_status", "cancelado")
    medico_substituto_id = post.get("medico_substituto") or None
    medico_substituto_confirmado = post.get("medico_substituto_confirmado") == "on"

    if medico_substituto_id:
        medico_atendido_id = medico_substituto_id
        confirmacao_medico = medico_substituto_confirmado
    else:
        medico_atendido_id = medico_inicial_id if medico_inicial_status == "confirmado" else None
        confirmacao_medico = medico_inicial_status == "confirmado"

    data_inicial = _parse_date(post.get("data_inicial"), datetime.date.today())
    data_final = _parse_date(post.get("data_final"), data_inicial)
    frequencia = post.get("frequencia", "unica")
    horario_inicio = post.get("horario_inicio") or "08:00"
    horario_fim = post.get("horario_fim") or "12:00"
    concierge = post.get("concierge", "")
    tipo_calculo_pagamento = post.get("tipo_calculo_pagamento") == "procedimento"
    valor_real = post.get("valor_real") or None

    procedimento_ids = post.getlist("procedimento[]")
    esperancas = post.getlist("esperanca_pacientes[]")
    reais = post.getlist("real_pacientes[]")

    if agenda:
        datas = [agenda.horario.data]
    elif frequencia == "semanal" and data_final > data_inicial:
        datas = []
        atual = data_inicial
        while atual <= data_final:
            datas.append(atual)
            atual += datetime.timedelta(days=7)
    else:
        datas = [data_inicial]

    agendas_salvas = []
    for data_evento in datas:
        if agenda:
            horario = agenda.horario
            horario.data = data_evento
            horario.horario_inicio = horario_inicio
            horario.horario_fim = horario_fim
            horario.save()
        else:
            horario = Horario.objects.create(
                data=data_evento, horario_inicio=horario_inicio, horario_fim=horario_fim
            )
            agenda = Agenda.objects.create(horario=horario)

        if sala:
            SalaHorario.objects.get_or_create(sala=sala, horario=horario)

        agenda.concierge = concierge
        agenda.tipo_calculo_pagamento = tipo_calculo_pagamento
        agenda.valor_real = valor_real
        agenda.confirmacao_medico = confirmacao_medico
        agenda.medico_inicial_id = medico_inicial_id
        agenda.medico_atendido_id = medico_atendido_id
        agenda.save()

        agenda.procedimentoagenda_set.all().delete()
        for idx, proc_id in enumerate(procedimento_ids):
            if not proc_id:
                continue
            esperanca = esperancas[idx] if idx < len(esperancas) and esperancas[idx] else 0
            real = reais[idx] if idx < len(reais) and reais[idx] else None
            ProcedimentoAgenda.objects.create(
                agenda=agenda,
                procedimento_id=proc_id,
                esperanca_pacientes=esperanca,
                real_pacientes=real or None,
            )

        agendas_salvas.append(agenda)
        agenda = None  # força criação de nova agenda/horario na próxima iteração (recorrência)

    return redirect("agendas:home")
