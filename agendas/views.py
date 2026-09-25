import calendar
import datetime
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from contas.decorators import cargo_required
from contas.models import Usuario

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
)

Cargo = Usuario.Cargo

DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
DIAS_SEMANA_ABREV = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
VIEWS_VALIDAS = ("dia", "semana", "mes", "ano")
VIEWS_LABELS = [("dia", "Dia"), ("semana", "Semana"), ("mes", "Mês"), ("ano", "Ano")]

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


def _somar_meses(dia, n):
    mes_total = dia.month - 1 + n
    ano = dia.year + mes_total // 12
    mes = mes_total % 12 + 1
    return dia.replace(year=ano, month=mes, day=1)


def _somar_anos(dia, n):
    try:
        return dia.replace(year=dia.year + n)
    except ValueError:
        return dia.replace(year=dia.year + n, day=28)


def _ultimo_dia_mes(primeiro_dia):
    proximo_mes = _somar_meses(primeiro_dia, 1)
    return proximo_mes - datetime.timedelta(days=1)


def _datas_recorrentes(data_inicial, data_final, dia_semana, intervalo_semanas):
    delta = (dia_semana - data_inicial.weekday()) % 7
    primeira = data_inicial + datetime.timedelta(days=delta)
    datas = []
    atual = primeira
    while atual <= data_final:
        datas.append(atual)
        atual += datetime.timedelta(weeks=intervalo_semanas)
    return datas


def _agenda_permitida(agenda, unidades_ids):
    """True se a agenda pode ser vista/editada pelo usuário (unidades_ids=None => sem restrição)."""
    if unidades_ids is None:
        return True
    sala = agenda.sala
    return sala is not None and sala.unidade_id in unidades_ids


def _agendas_no_intervalo(inicio, fim, unidade_filtro, busca, unidades_ids=None):
    agendas_qs = (
        Agenda.objects.select_related("horario", "medico_inicial", "medico_atendido")
        .prefetch_related("horario__salas__unidade")
        .filter(horario__data__range=[inicio, fim])
    )
    if unidades_ids is not None:
        agendas_qs = agendas_qs.filter(horario__salas__unidade_id__in=unidades_ids)
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
    return agendas_qs.distinct().order_by("horario__data", "horario__horario_inicio")


def _montar_dia(dia, agendas_qs, nome=None):
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
                "turno": ag.horario.turno,
            }
        )
    turnos = {"Manhã": [], "Tarde": [], "Noite": []}
    for evento in eventos:
        turnos[evento["turno"]].append(evento)

    resultado = {"data": dia, "eventos": eventos, "turnos": turnos}
    if nome:
        resultado["nome"] = nome
    return resultado


def _cores_por_dia(data_inicio, data_fim, unidades_ids=None):
    cores = defaultdict(list)
    agendas = (
        Agenda.objects.select_related("horario")
        .prefetch_related("horario__salas__unidade")
        .filter(horario__data__range=[data_inicio, data_fim])
    )
    if unidades_ids is not None:
        agendas = agendas.filter(horario__salas__unidade_id__in=unidades_ids)
    agendas = agendas.distinct().order_by("horario__data", "horario__horario_inicio")
    for ag in agendas:
        sala = ag.sala
        cor = _cor_unidade(sala.unidade_id if sala else None)
        dia_cores = cores[ag.horario.data]
        if cor not in dia_cores and len(dia_cores) < 3:
            dia_cores.append(cor)
    return cores


def _construir_mini_mes(ano, mes, unidades_ids=None):
    mes_ref = datetime.date(ano, mes, 1)
    cal = calendar.Calendar(firstweekday=0)
    semanas_mes = cal.monthdatescalendar(ano, mes)
    cores_por_dia = _cores_por_dia(semanas_mes[0][0], semanas_mes[-1][-1], unidades_ids)
    return {"mes_ref": mes_ref, "semanas_mes": semanas_mes, "cores_por_dia": cores_por_dia}


def _agendas_abertas(hoje, primeiro_dia_mes, ultimo_dia_mes, unidades_ids=None):
    abertas_qs = (
        Agenda.objects.select_related("horario")
        .prefetch_related("horario__salas__unidade")
        .filter(medico_inicial__isnull=True, horario__data__range=[primeiro_dia_mes, ultimo_dia_mes])
    )
    if unidades_ids is not None:
        abertas_qs = abertas_qs.filter(horario__salas__unidade_id__in=unidades_ids)
    abertas_qs = abertas_qs.distinct().order_by("horario__data", "horario__horario_inicio")

    agrupado = defaultdict(list)
    for ag in abertas_qs:
        sala = ag.sala
        unidade = sala.unidade if sala else None
        dias_ate = (ag.horario.data - hoje).days
        agrupado[ag.horario.data].append(
            {
                "agenda": ag,
                "unidade": unidade,
                "especialidade": sala.especialidade if sala else "",
                "turno": ag.horario.turno,
                "cor": _cor_unidade(unidade.id if unidade else None),
                "urgente": 0 <= dias_ate <= 15,
            }
        )

    amanha = hoje + datetime.timedelta(days=1)
    grupos = []
    for dia, itens in sorted(agrupado.items()):
        if dia == hoje:
            rotulo = "HOJE"
        elif dia == amanha:
            rotulo = "AMANHÃ"
        else:
            nome = DIAS_SEMANA[dia.weekday()].upper()
            rotulo = f"{nome}-FEIRA" if dia.weekday() < 5 else nome
        grupos.append({"data": dia, "rotulo": rotulo, "itens": itens})
    return grupos


def _contexto_dia(data_ref, unidade_filtro, busca, unidades_ids=None):
    agendas_qs = _agendas_no_intervalo(data_ref, data_ref, unidade_filtro, busca, unidades_ids)
    dia_atual = _montar_dia(data_ref, agendas_qs, nome=DIAS_SEMANA[data_ref.weekday()])
    return {
        "dia_atual": dia_atual,
        "anterior": (data_ref - datetime.timedelta(days=1)).isoformat(),
        "proximo": (data_ref + datetime.timedelta(days=1)).isoformat(),
    }


def _contexto_semana(data_ref, unidade_filtro, busca, unidades_ids=None):
    inicio_semana = _monday(data_ref)
    fim_semana = inicio_semana + datetime.timedelta(days=6)
    agendas_qs = _agendas_no_intervalo(inicio_semana, fim_semana, unidade_filtro, busca, unidades_ids)
    dias_semana = [
        _montar_dia(inicio_semana + datetime.timedelta(days=i), agendas_qs, nome=DIAS_SEMANA[i])
        for i in range(7)
    ]
    return {
        "inicio_semana": inicio_semana,
        "fim_semana": fim_semana,
        "dias_semana": dias_semana,
        "anterior": (inicio_semana - datetime.timedelta(days=7)).isoformat(),
        "proximo": (inicio_semana + datetime.timedelta(days=7)).isoformat(),
    }


def _contexto_mes(data_ref, unidade_filtro, busca, unidades_ids=None):
    mes_ref = data_ref.replace(day=1)
    cal = calendar.Calendar(firstweekday=0)
    semanas_mes = cal.monthdatescalendar(mes_ref.year, mes_ref.month)
    agendas_qs = _agendas_no_intervalo(
        semanas_mes[0][0], semanas_mes[-1][-1], unidade_filtro, busca, unidades_ids
    )

    grid = []
    for semana in semanas_mes:
        linha = []
        for dia in semana:
            montado = _montar_dia(dia, agendas_qs)
            eventos = montado["eventos"]
            linha.append(
                {
                    "data": dia,
                    "outro_mes": dia.month != mes_ref.month,
                    "eventos_resumo": eventos[:3],
                    "eventos_extra": max(0, len(eventos) - 3),
                }
            )
        grid.append(linha)

    return {
        "mes_atual_ref": mes_ref,
        "grid_mes": grid,
        "anterior": _somar_meses(mes_ref, -1).isoformat(),
        "proximo": _somar_meses(mes_ref, 1).isoformat(),
    }


def _contexto_ano(data_ref, unidade_filtro, busca, unidades_ids=None):
    ano_ref = data_ref.year
    meses_ano = []
    for mes in range(1, 13):
        info = _construir_mini_mes(ano_ref, mes, unidades_ids)
        info["link"] = f"?view=mes&data={info['mes_ref'].isoformat()}&q={busca}&unidade={unidade_filtro}"
        meses_ano.append(info)
    return {
        "ano_ref": ano_ref,
        "meses_ano": meses_ano,
        "anterior": _somar_anos(data_ref, -1).isoformat(),
        "proximo": _somar_anos(data_ref, 1).isoformat(),
    }


@login_required
def home(request):
    hoje = datetime.date.today()
    view = request.GET.get("view", "semana")
    if view not in VIEWS_VALIDAS:
        view = "semana"

    data_param = request.GET.get("data") or request.GET.get("semana")
    data_ref = _parse_date(data_param, hoje)

    busca = request.GET.get("q", "").strip()
    unidade_filtro = request.GET.get("unidade", "").strip()

    unidades_ids = request.user.unidades_ids()
    unidades_qs = Unidade.objects.all()
    if unidades_ids is not None:
        unidades_qs = unidades_qs.filter(id__in=unidades_ids)
        if not unidade_filtro.isdigit() or int(unidade_filtro) not in unidades_ids:
            unidade_filtro = ""

    construtores = {
        "dia": _contexto_dia,
        "semana": _contexto_semana,
        "mes": _contexto_mes,
        "ano": _contexto_ano,
    }
    contexto_view = construtores[view](data_ref, unidade_filtro, busca, unidades_ids)

    mes_mini_ref = contexto_view.get("inicio_semana", data_ref)
    mini_mes = _construir_mini_mes(mes_mini_ref.year, mes_mini_ref.month, unidades_ids)

    primeiro_dia_mes = mini_mes["mes_ref"]
    ultimo_dia_mes = _ultimo_dia_mes(primeiro_dia_mes)
    agendas_abertas_grupos = _agendas_abertas(hoje, primeiro_dia_mes, ultimo_dia_mes, unidades_ids)

    context = {
        "view": view,
        "views_labels": VIEWS_LABELS,
        "data_ref": data_ref.isoformat(),
        "hoje": hoje,
        "unidades": unidades_qs,
        "busca": busca,
        "unidade_filtro": unidade_filtro,
        "mes_ref": mini_mes["mes_ref"],
        "semanas_mes": mini_mes["semanas_mes"],
        "cores_por_dia": mini_mes["cores_por_dia"],
        "agendas_abertas_grupos": agendas_abertas_grupos,
    }
    context.update(contexto_view)
    return render(request, "agendas/home.html", context)


@login_required
def lista_agendamentos(request, data):
    dia = _parse_date(data, datetime.date.today())
    busca = request.GET.get("q", "").strip()
    ordenar = request.GET.get("ordenar", "recentes")
    unidades_ids = request.user.unidades_ids()

    agendas_qs = (
        Agenda.objects.select_related("horario", "medico_inicial", "medico_atendido")
        .prefetch_related("horario__salas__unidade", "procedimentoagenda_set__procedimento")
        .filter(horario__data=dia)
    )
    if unidades_ids is not None:
        agendas_qs = agendas_qs.filter(horario__salas__unidade_id__in=unidades_ids)

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


@login_required
def cadastro_agenda(request, agenda_id=None):
    if request.user.cargo == Cargo.CONCIERGE:
        if not agenda_id:
            raise PermissionDenied
        return _editar_pacientes_reais(request, agenda_id)

    unidades_ids = request.user.unidades_ids()

    agenda = None
    if agenda_id:
        agenda = get_object_or_404(
            Agenda.objects.select_related("horario", "medico_inicial", "medico_atendido").prefetch_related(
                "horario__salas__unidade", "procedimentoagenda_set__procedimento"
            ),
            pk=agenda_id,
        )
        if not _agenda_permitida(agenda, unidades_ids):
            raise PermissionDenied

    if request.method == "POST":
        return _salvar_agenda(request, agenda, unidades_ids)

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

    unidades_qs = Unidade.objects.all()
    salas_qs = Sala.objects.select_related("unidade").all()
    medicos_qs = Medico.objects.all()
    procedimentos_qs = Procedimento.objects.select_related("unidade").all()
    if unidades_ids is not None:
        unidades_qs = unidades_qs.filter(id__in=unidades_ids)
        salas_qs = salas_qs.filter(unidade_id__in=unidades_ids)
        medicos_qs = medicos_qs.filter(unidades__id__in=unidades_ids).distinct()
        procedimentos_qs = procedimentos_qs.filter(unidade_id__in=unidades_ids)

    context = {
        "agenda": agenda,
        "unidades": unidades_qs,
        "salas": salas_qs,
        "medicos": medicos_qs,
        "procedimentos": procedimentos_qs,
        "unidade_pref_id": str(unidade_pref_id) if unidade_pref_id else "",
        "sala_pref": sala_pref,
        "data_pref": data_pref,
        "horario_inicio_pref": horario_inicio_pref,
        "horario_fim_pref": horario_fim_pref,
        "procedimentos_agenda": procedimentos_agenda,
        "dias_semana_opcoes": list(enumerate(DIAS_SEMANA_ABREV)),
        "pode_excluir": agenda is not None,
    }
    return render(request, "agendas/partials/_cadastro_agenda.html", context)


@transaction.atomic
def _salvar_agenda(request, agenda, unidades_ids):
    post = request.POST

    sala_id = post.get("sala")
    sala = get_object_or_404(Sala, pk=sala_id) if sala_id else None
    if sala and unidades_ids is not None and sala.unidade_id not in unidades_ids:
        raise PermissionDenied

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

    procedimento_ids = post.getlist("procedimento[]")
    esperancas = post.getlist("esperanca_pacientes[]")
    reais = post.getlist("real_pacientes[]")

    if agenda:
        datas = [agenda.horario.data]
    elif frequencia == "semanal" and data_final > data_inicial:
        dia_semana = post.get("dia_semana")
        dia_semana = int(dia_semana) if dia_semana is not None and dia_semana != "" else data_inicial.weekday()
        intervalo_semanas = 2 if post.get("intervalo_semanas") == "2" else 1
        datas = _datas_recorrentes(data_inicial, data_final, dia_semana, intervalo_semanas)
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


def _editar_pacientes_reais(request, agenda_id):
    unidades_ids = request.user.unidades_ids()
    agenda = get_object_or_404(
        Agenda.objects.select_related("horario", "medico_inicial", "medico_atendido").prefetch_related(
            "horario__salas__unidade", "procedimentoagenda_set__procedimento"
        ),
        pk=agenda_id,
    )
    if not _agenda_permitida(agenda, unidades_ids):
        raise PermissionDenied

    if request.method == "POST":
        pa_ids = request.POST.getlist("procedimento_agenda_id[]")
        reais = request.POST.getlist("real_pacientes[]")
        for pa_id, real in zip(pa_ids, reais):
            ProcedimentoAgenda.objects.filter(pk=pa_id, agenda=agenda).update(real_pacientes=real or None)
        return redirect("agendas:home")

    procedimentos_agenda = list(agenda.procedimentoagenda_set.select_related("procedimento"))
    context = {
        "agenda": agenda,
        "sala": agenda.sala,
        "unidade": agenda.unidade,
        "procedimentos_agenda": procedimentos_agenda,
    }
    return render(request, "agendas/partials/_editar_pacientes_reais.html", context)


@cargo_required(Cargo.ADMINISTRADOR, Cargo.AGENDAMENTO)
def excluir_agenda(request, agenda_id):
    unidades_ids = request.user.unidades_ids()
    agenda = get_object_or_404(Agenda, pk=agenda_id)
    if not _agenda_permitida(agenda, unidades_ids):
        raise PermissionDenied

    if request.method == "POST":
        horario = agenda.horario
        agenda.delete()
        horario.delete()
    return redirect("agendas:home")


@cargo_required(Cargo.ADMINISTRADOR, Cargo.AGENDAMENTO)
def medicos_lista(request):
    unidades_ids = request.user.unidades_ids()
    medicos_qs = Medico.objects.select_related("conta_bancaria").prefetch_related("unidades").all()
    if unidades_ids is not None:
        medicos_qs = medicos_qs.filter(unidades__id__in=unidades_ids).distinct()
    return render(request, "agendas/medicos_lista.html", {"medicos": medicos_qs.order_by("nome")})


@cargo_required(Cargo.ADMINISTRADOR, Cargo.AGENDAMENTO)
def medico_form(request, medico_id=None):
    unidades_ids = request.user.unidades_ids()

    medico = None
    if medico_id:
        medico = get_object_or_404(Medico.objects.prefetch_related("unidades"), pk=medico_id)
        if unidades_ids is not None and not medico.unidades.filter(id__in=unidades_ids).exists():
            raise PermissionDenied

    if request.method == "POST":
        post = request.POST
        unidades_marcadas = {int(v) for v in post.getlist("unidades") if v}
        if unidades_ids is not None:
            unidades_marcadas &= unidades_ids

        if medico is None:
            medico = Medico()
        medico.nome = post.get("nome", "").strip()
        medico.email = post.get("email", "").strip()
        medico.telefone = post.get("telefone", "").strip()
        medico.especialidade = post.get("especialidade", "").strip()
        medico.conta_bancaria_id = post.get("conta_bancaria") or None
        medico.save()

        if unidades_ids is None:
            medico.unidades.set(unidades_marcadas)
        else:
            # Agendamento só pode alterar o vínculo com as unidades que ele enxerga;
            # vínculos com outras unidades do médico permanecem intocados.
            fora_do_escopo = set(medico.unidades.exclude(id__in=unidades_ids).values_list("id", flat=True))
            medico.unidades.set(unidades_marcadas | fora_do_escopo)

        return redirect("agendas:medicos_lista")

    unidades_qs = Unidade.objects.all()
    if unidades_ids is not None:
        unidades_qs = unidades_qs.filter(id__in=unidades_ids)
    unidades_do_medico = set(medico.unidades.values_list("id", flat=True)) if medico else set()

    context = {
        "medico": medico,
        "unidades": unidades_qs,
        "unidades_do_medico": unidades_do_medico,
        "contas_bancarias": ContaBancaria.objects.all(),
    }
    return render(request, "agendas/partials/_medico_form.html", context)


@cargo_required(Cargo.ADMINISTRADOR, Cargo.AGENDAMENTO)
def medico_excluir(request, medico_id):
    unidades_ids = request.user.unidades_ids()
    medico = get_object_or_404(Medico, pk=medico_id)
    if unidades_ids is not None and not medico.unidades.filter(id__in=unidades_ids).exists():
        raise PermissionDenied

    if request.method == "POST":
        medico.delete()
    return redirect("agendas:medicos_lista")
