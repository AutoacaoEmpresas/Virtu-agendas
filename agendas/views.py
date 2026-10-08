import calendar
import csv
import datetime
from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from contas.decorators import cargo_required
from contas.models import Usuario

from . import historico, repasse
from .utils import parse_mes, somar_meses, ultimo_dia_mes
from .models import (
    Agenda,
    ContaBancaria,
    FechamentoRepasse,
    Horario,
    LogAgenda,
    Medico,
    Procedimento,
    ProcedimentoAgenda,
    Recorrencia,
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


def _somar_anos(dia, n):
    try:
        return dia.replace(year=dia.year + n)
    except ValueError:
        return dia.replace(year=dia.year + n, day=28)


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
        "anterior": somar_meses(mes_ref, -1).isoformat(),
        "proximo": somar_meses(mes_ref, 1).isoformat(),
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
    fim_mes = ultimo_dia_mes(primeiro_dia_mes)
    agendas_abertas_grupos = _agendas_abertas(hoje, primeiro_dia_mes, fim_mes, unidades_ids)

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
            Agenda.objects.select_related("horario", "medico_inicial", "medico_atendido", "recorrencia").prefetch_related(
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

    # Datas das agendas da mesma recorrência a partir desta (usadas pelo JS para avisar
    # quantas serão excluídas ao encurtar a data final).
    datas_recorrencia = []
    if agenda and agenda.recorrencia_id:
        datas_recorrencia = list(
            Horario.objects.filter(
                agenda__recorrencia_id=agenda.recorrencia_id, data__gt=agenda.horario.data
            ).values_list("data", flat=True)
        )

    unidades_qs = Unidade.objects.all()
    salas_qs = Sala.objects.select_related("unidade").all()
    medicos_qs = Medico.objects.prefetch_related("unidades")
    procedimentos_qs = Procedimento.objects.select_related("unidade").order_by("nome_procedimento")
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
        "recorrencia": agenda.recorrencia if agenda else None,
        "datas_recorrencia": ",".join(d.isoformat() for d in datas_recorrencia),
        "travada": agenda is not None and repasse.agenda_travada(agenda),
    }
    return render(request, "agendas/partials/_cadastro_agenda.html", context)


@transaction.atomic
def _salvar_agenda(request, agenda, unidades_ids):
    post = request.POST

    if agenda and repasse.agenda_travada(agenda):
        messages.error(request, f"A agenda #{agenda.id} já está em um repasse fechado e não pode ser alterada.")
        return redirect("agendas:home")

    sala_id = post.get("sala")
    sala = get_object_or_404(Sala, pk=sala_id) if sala_id else None
    if sala and unidades_ids is not None and sala.unidade_id not in unidades_ids:
        raise PermissionDenied

    # Depois de alocado, o médico inicial não muda: só o status dele (e o substituto, se cancelar).
    if agenda and agenda.medico_inicial_id:
        medico_inicial_id = agenda.medico_inicial_id
    else:
        medico_inicial_id = post.get("medico_inicial") or None

    Status = Agenda.StatusMedicoInicial
    status_medico_inicial = post.get("medico_inicial_status")
    if not medico_inicial_id or status_medico_inicial not in (Status.CONFIRMADO, Status.CANCELADO):
        status_medico_inicial = Status.PENDENTE

    medico_substituto_id = post.get("medico_substituto") or None
    if medico_substituto_id == str(medico_inicial_id):
        medico_substituto_id = None
    medico_substituto_confirmado = post.get("medico_substituto_confirmado") == "on"

    if status_medico_inicial == Status.CONFIRMADO:
        medico_atendido_id = medico_inicial_id
        confirmacao_medico = True
    elif status_medico_inicial == Status.CANCELADO and medico_substituto_id:
        medico_atendido_id = medico_substituto_id
        confirmacao_medico = medico_substituto_confirmado
    else:
        medico_atendido_id = None
        confirmacao_medico = False

    data_inicial = _parse_date(post.get("data_inicial"), datetime.date.today())
    data_final = _parse_date(post.get("data_final"), data_inicial)
    frequencia = post.get("frequencia", "unica")
    horario_inicio = post.get("horario_inicio") or "08:00"
    horario_fim = post.get("horario_fim") or "12:00"
    concierge = post.get("concierge", "")

    procedimento_ids = post.getlist("procedimento[]")
    esperancas = post.getlist("esperanca_pacientes[]")
    reais = post.getlist("real_pacientes[]")

    # Procedimentos exclusivos só podem ser usados pelo médico a que pertencem.
    medicos_da_agenda = {str(m) for m in (medico_inicial_id, medico_atendido_id) if m}
    exclusivos = Procedimento.objects.filter(
        id__in=[p for p in procedimento_ids if p], medico_exclusivo__isnull=False
    ).select_related("medico_exclusivo")
    for proc in exclusivos:
        if str(proc.medico_exclusivo_id) not in medicos_da_agenda:
            messages.error(
                request,
                f"O procedimento \"{proc.nome_procedimento}\" é exclusivo de {proc.medico_exclusivo.nome}. "
                "A agenda não foi salva.",
            )
            return redirect("agendas:home")

    antes = historico.snapshot(agenda) if agenda else None
    alteracoes_extras = []
    recorrencia = None
    if agenda:
        datas = [data_inicial]
        if agenda.recorrencia_id:
            alteracoes_extras = _encurtar_recorrencia(agenda, data_final, data_inicial)
    elif frequencia == "semanal" and data_final > data_inicial:
        dia_semana = post.get("dia_semana")
        dia_semana = int(dia_semana) if dia_semana is not None and dia_semana != "" else data_inicial.weekday()
        intervalo_semanas = 2 if post.get("intervalo_semanas") == "2" else 1
        datas = _datas_recorrentes(data_inicial, data_final, dia_semana, intervalo_semanas)
        if len(datas) > 1:
            recorrencia = Recorrencia.objects.create(
                data_inicial=data_inicial,
                data_final=data_final,
                dia_semana=dia_semana,
                intervalo_semanas=intervalo_semanas,
            )
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
            agenda = Agenda.objects.create(horario=horario, recorrencia=recorrencia)

        if sala:
            SalaHorario.objects.filter(horario=horario).exclude(sala=sala).delete()
            SalaHorario.objects.get_or_create(sala=sala, horario=horario)

        agenda.concierge = concierge
        agenda.confirmacao_medico = confirmacao_medico
        agenda.status_medico_inicial = status_medico_inicial
        agenda.medico_inicial_id = medico_inicial_id
        agenda.medico_atendido_id = medico_atendido_id
        _aplicar_realizacao(agenda, post, request.user)
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

    _registrar_salvamento(request.user, antes, agendas_salvas, recorrencia, alteracoes_extras)
    return redirect("agendas:home")


def _aplicar_realizacao(agenda, post, usuario):
    """Campos de realização (chegada/saída do médico). Só agendas realizadas entram no repasse."""
    if "realizacao" not in post:
        return
    realizada = post.get("realizada") == "on"
    if realizada and not agenda.realizada:
        agenda.realizada_em = timezone.now()
        agenda.realizada_por = usuario
    elif not realizada:
        agenda.realizada_em = None
        agenda.realizada_por = None
    agenda.realizada = realizada
    agenda.hora_chegada = post.get("hora_chegada") or None
    agenda.hora_saida = post.get("hora_saida") or None


def _registrar_salvamento(usuario, antes, agendas_salvas, recorrencia, alteracoes_extras):
    """Uma única linha de histórico por clique em Salvar (mesmo quando gera várias agendas)."""
    primeira = historico.carregar(agendas_salvas[0].id)
    depois = historico.snapshot(primeira)

    if antes:
        alteracoes = historico.diferencas(antes, depois) + alteracoes_extras
        historico.registrar(usuario, LogAgenda.Acao.MODIFICACAO, primeira, alteracoes)
    elif recorrencia:
        depois.pop("Data")
        alteracoes = historico.como_cadastro(depois) + [
            {"campo": "Recorrência", "antes": "", "depois": historico.descrever_recorrencia(recorrencia)},
            {"campo": "Agendas criadas", "antes": "", "depois": historico.lista_datas(agendas_salvas)},
        ]
        resumo_texto = f"Recorrência com {len(agendas_salvas)} agendas · {historico.resumo(primeira)}"
        historico.registrar(usuario, LogAgenda.Acao.CADASTRO, primeira, alteracoes, resumo_texto)
    else:
        historico.registrar(usuario, LogAgenda.Acao.CADASTRO, primeira, historico.como_cadastro(depois))


def _encurtar_recorrencia(agenda, nova_data_final, data_agenda):
    """Antecipa a data final da recorrência da agenda, excluindo as agendas posteriores a ela.

    A nova data final nunca fica antes da própria agenda em edição (que nunca é excluída aqui),
    e só é possível encurtar (estender exigiria gerar novas agendas).
    Retorna as alterações para o histórico.
    """
    recorrencia = agenda.recorrencia
    nova_data_final = max(nova_data_final, data_agenda)
    if nova_data_final >= recorrencia.data_final:
        return []

    excluidas = list(
        Agenda.objects.select_related("horario")
        .filter(recorrencia=recorrencia, horario__data__gt=nova_data_final)
        .exclude(pk=agenda.pk)
        .order_by("horario__data")
    )
    alteracoes = [
        {
            "campo": "Data final da recorrência",
            "antes": f"{recorrencia.data_final:%d/%m/%Y}",
            "depois": f"{nova_data_final:%d/%m/%Y}",
        }
    ]
    if excluidas:
        alteracoes.append(
            {"campo": "Agendas excluídas da recorrência", "antes": historico.lista_datas(excluidas), "depois": ""}
        )

    # Excluir o Horario remove em cascata a Agenda, a SalaHorario e os ProcedimentoAgenda.
    Horario.objects.filter(agenda__in=excluidas).delete()
    recorrencia.data_final = nova_data_final
    recorrencia.save(update_fields=["data_final"])
    return alteracoes


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
    travada = repasse.agenda_travada(agenda)

    if request.method == "POST":
        if travada:
            messages.error(request, f"A agenda #{agenda.id} já está em um repasse fechado e não pode ser alterada.")
            return redirect("agendas:home")
        antes = historico.snapshot(agenda)
        pa_ids = request.POST.getlist("procedimento_agenda_id[]")
        reais = request.POST.getlist("real_pacientes[]")
        with transaction.atomic():
            for pa_id, real in zip(pa_ids, reais):
                ProcedimentoAgenda.objects.filter(pk=pa_id, agenda=agenda).update(real_pacientes=real or None)
            _aplicar_realizacao(agenda, request.POST, request.user)
            agenda.save()
            alteracoes = historico.diferencas(antes, historico.snapshot(historico.carregar(agenda.id)))
            historico.registrar(request.user, LogAgenda.Acao.MODIFICACAO, agenda, alteracoes)
        return redirect("agendas:home")

    procedimentos_agenda = list(agenda.procedimentoagenda_set.select_related("procedimento"))
    context = {
        "agenda": agenda,
        "sala": agenda.sala,
        "unidade": agenda.unidade,
        "procedimentos_agenda": procedimentos_agenda,
        "travada": travada,
    }
    return render(request, "agendas/partials/_editar_pacientes_reais.html", context)


@cargo_required(Cargo.ADMINISTRADOR, Cargo.AGENDAMENTO)
def excluir_agenda(request, agenda_id):
    unidades_ids = request.user.unidades_ids()
    agenda = get_object_or_404(Agenda, pk=agenda_id)
    if not _agenda_permitida(agenda, unidades_ids):
        raise PermissionDenied

    if request.method == "POST":
        with transaction.atomic():
            _excluir_agenda(request, agenda)
    return redirect("agendas:home")


def _excluir_agenda(request, agenda):
    recorrencia = agenda.recorrencia
    alteracoes = historico.como_exclusao(historico.snapshot(agenda))
    resumo_texto = historico.resumo(agenda)

    if recorrencia and request.POST.get("escopo") == "posteriores":
        excluidas = list(
            Agenda.objects.select_related("horario")
            .filter(recorrencia=recorrencia, horario__data__gte=agenda.horario.data)
            .order_by("horario__data")
        )
        alteracoes.append({"campo": "Agendas excluídas", "antes": historico.lista_datas(excluidas), "depois": ""})
        resumo_texto = f"Esta e as posteriores da recorrência ({len(excluidas)} agendas) · {resumo_texto}"
        historico.registrar(request.user, LogAgenda.Acao.EXCLUSAO, agenda, alteracoes, resumo_texto)
        # Excluir o Horario remove em cascata a Agenda, a SalaHorario e os ProcedimentoAgenda.
        Horario.objects.filter(agenda__in=excluidas).delete()
    else:
        historico.registrar(request.user, LogAgenda.Acao.EXCLUSAO, agenda, alteracoes, resumo_texto)
        horario = agenda.horario
        agenda.delete()
        horario.delete()

    if recorrencia:
        _ajustar_fim_recorrencia(recorrencia)


def _ajustar_fim_recorrencia(recorrencia):
    """Após exclusões, faz a data final acompanhar a última agenda restante (ou remove a série vazia)."""
    ultima_data = (
        Horario.objects.filter(agenda__recorrencia=recorrencia).order_by("-data").values_list("data", flat=True).first()
    )
    if ultima_data is None:
        recorrencia.delete()
    elif ultima_data != recorrencia.data_final:
        recorrencia.data_final = ultima_data
        recorrencia.save(update_fields=["data_final"])


@cargo_required(Cargo.ADMINISTRADOR)
def historico_agendas(request):
    acao = request.GET.get("acao", "")
    usuario_id = request.GET.get("usuario", "")
    unidade_id = request.GET.get("unidade", "")
    busca = request.GET.get("q", "").strip()

    logs = LogAgenda.objects.select_related("unidade")
    if acao:
        logs = logs.filter(acao=acao)
    if usuario_id:
        logs = logs.filter(usuario_id=usuario_id)
    if unidade_id:
        logs = logs.filter(unidade_id=unidade_id)
    if busca:
        filtro = Q(resumo__icontains=busca) | Q(usuario_nome__icontains=busca)
        numero = busca.lstrip("#")
        if numero.isdigit():
            filtro |= Q(agenda_numero=int(numero))
        logs = logs.filter(filtro)

    pagina = Paginator(logs, 50).get_page(request.GET.get("pagina"))
    filtros = request.GET.copy()
    filtros.pop("pagina", None)
    context = {
        "em_area_historico": True,
        "pagina": pagina,
        "acoes": LogAgenda.Acao.choices,
        "usuarios": Usuario.objects.filter(logs_agenda__isnull=False).distinct().order_by("username"),
        "unidades": Unidade.objects.all(),
        "acao": acao,
        "usuario_id": usuario_id,
        "unidade_id": unidade_id,
        "busca": busca,
        "filtros_query": filtros.urlencode(),
    }
    return render(request, "agendas/historico.html", context)


@cargo_required(Cargo.ADMINISTRADOR)
def cadastros_home(request):
    context = {
        "em_area_cadastros": True,
        "cadastro_ativo": None,
        "total_medicos": Medico.objects.count(),
        "total_concierges": Usuario.objects.filter(cargo=Cargo.CONCIERGE).count(),
        "total_procedimentos": Procedimento.objects.count(),
    }
    return render(request, "agendas/cadastros_home.html", context)


@cargo_required(Cargo.ADMINISTRADOR)
def medicos_lista(request):
    medicos_qs = Medico.objects.select_related("conta_bancaria").prefetch_related("unidades").order_by("nome")
    context = {"medicos": medicos_qs, "em_area_cadastros": True, "cadastro_ativo": "medicos"}
    return render(request, "agendas/medicos_lista.html", context)


@cargo_required(Cargo.ADMINISTRADOR)
def medico_form(request, medico_id=None):
    medico = get_object_or_404(Medico.objects.prefetch_related("unidades"), pk=medico_id) if medico_id else None

    if request.method == "POST":
        post = request.POST
        unidades_marcadas = {int(v) for v in post.getlist("unidades") if v}

        if medico is None:
            medico = Medico()
        medico.nome = post.get("nome", "").strip()
        medico.email = post.get("email", "").strip()
        medico.telefone = post.get("telefone", "").strip()
        medico.especialidade = post.get("especialidade", "").strip()
        medico.conta_bancaria_id = post.get("conta_bancaria") or None
        medico.save()
        medico.unidades.set(unidades_marcadas)

        return redirect("agendas:medicos_lista")

    unidades_do_medico = set(medico.unidades.values_list("id", flat=True)) if medico else set()
    context = {
        "medico": medico,
        "unidades": Unidade.objects.all(),
        "unidades_do_medico": unidades_do_medico,
        "contas_bancarias": ContaBancaria.objects.all(),
    }
    return render(request, "agendas/partials/_medico_form.html", context)


@cargo_required(Cargo.ADMINISTRADOR)
def medico_excluir(request, medico_id):
    medico = get_object_or_404(Medico, pk=medico_id)
    if request.method == "POST":
        medico.delete()
    return redirect("agendas:medicos_lista")


@cargo_required(Cargo.ADMINISTRADOR)
def concierges_lista(request):
    concierges_qs = Usuario.objects.filter(cargo=Cargo.CONCIERGE).prefetch_related("unidades_permitidas").order_by(
        "username"
    )
    context = {"concierges": concierges_qs, "em_area_cadastros": True, "cadastro_ativo": "concierges"}
    return render(request, "agendas/concierges_lista.html", context)


@cargo_required(Cargo.ADMINISTRADOR)
def concierge_form(request, usuario_id=None):
    concierge = (
        get_object_or_404(Usuario, pk=usuario_id, cargo=Cargo.CONCIERGE)
        if usuario_id
        else None
    )

    if request.method == "POST":
        post = request.POST
        username = post.get("username", "").strip()
        senha = post.get("senha", "")
        unidades_marcadas = {int(v) for v in post.getlist("unidades") if v}

        if not username or (not concierge and not senha):
            context = {
                "concierge": concierge,
                "unidades": Unidade.objects.all(),
                "unidades_do_concierge": unidades_marcadas,
                "erro": "Usuário e senha são obrigatórios.",
            }
            return render(request, "agendas/partials/_concierge_form.html", context)

        if Usuario.objects.filter(username=username).exclude(pk=concierge.pk if concierge else None).exists():
            context = {
                "concierge": concierge,
                "unidades": Unidade.objects.all(),
                "unidades_do_concierge": unidades_marcadas,
                "erro": "Já existe um usuário com esse nome.",
            }
            return render(request, "agendas/partials/_concierge_form.html", context)

        if concierge is None:
            concierge = Usuario(cargo=Cargo.CONCIERGE)
        concierge.username = username
        concierge.email = post.get("email", "").strip()
        concierge.is_active = post.get("ativo") == "on"
        if senha:
            concierge.set_password(senha)
        concierge.save()
        concierge.unidades_permitidas.set(unidades_marcadas)

        return redirect("agendas:concierges_lista")

    unidades_do_concierge = (
        set(concierge.unidades_permitidas.values_list("id", flat=True)) if concierge else set()
    )
    context = {
        "concierge": concierge,
        "unidades": Unidade.objects.all(),
        "unidades_do_concierge": unidades_do_concierge,
    }
    return render(request, "agendas/partials/_concierge_form.html", context)


@cargo_required(Cargo.ADMINISTRADOR)
def concierge_excluir(request, usuario_id):
    concierge = get_object_or_404(Usuario, pk=usuario_id, cargo=Cargo.CONCIERGE)
    if request.method == "POST":
        concierge.delete()
    return redirect("agendas:concierges_lista")


@cargo_required(Cargo.ADMINISTRADOR)
def procedimentos_lista(request):
    procedimentos_qs = Procedimento.objects.select_related("unidade", "medico_exclusivo").order_by(
        "unidade__nome", "nome_procedimento"
    )
    context = {"procedimentos": procedimentos_qs, "em_area_cadastros": True, "cadastro_ativo": "procedimentos"}
    return render(request, "agendas/procedimentos_lista.html", context)


@cargo_required(Cargo.ADMINISTRADOR)
def procedimento_form(request, procedimento_id=None):
    procedimento = get_object_or_404(Procedimento, pk=procedimento_id) if procedimento_id else None

    if request.method == "POST":
        post = request.POST
        if procedimento is None:
            procedimento = Procedimento()
        procedimento.nome_procedimento = post.get("nome_procedimento", "").strip()
        procedimento.especialidade = post.get("especialidade", "").strip()
        procedimento.unidade_id = post.get("unidade")
        procedimento.valor_base = Decimal(post.get("valor_base") or "0")
        procedimento.tipo_calculo = post.get("tipo_calculo") or Procedimento.TipoCalculo.PROCEDIMENTO
        procedimento.prazo_repasse_meses = int(post.get("prazo_repasse_meses") or 1)
        procedimento.medico_exclusivo_id = post.get("medico_exclusivo") or None
        procedimento.save()
        return redirect("agendas:procedimentos_lista")

    context = {
        "procedimento": procedimento,
        "unidades": Unidade.objects.all(),
        "medicos": Medico.objects.order_by("nome"),
        "tipos_calculo": Procedimento.TipoCalculo.choices,
        "prazos": Procedimento.PRAZO_REPASSE_CHOICES,
    }
    return render(request, "agendas/partials/_procedimento_form.html", context)


@cargo_required(Cargo.ADMINISTRADOR)
def procedimento_excluir(request, procedimento_id):
    procedimento = get_object_or_404(Procedimento, pk=procedimento_id)
    if request.method == "POST":
        if procedimento.agendas.exists():
            messages.error(request, "Este procedimento já foi usado em agendas e não pode ser excluído.")
        else:
            procedimento.delete()
    return redirect("agendas:procedimentos_lista")


def _competencia_param(request):
    """Mês de pagamento (?mes=AAAA-MM); padrão: mês seguinte."""
    return parse_mes(request.GET.get("mes") or request.POST.get("mes"), somar_meses(datetime.date.today(), 1))


@cargo_required(Cargo.ADMINISTRADOR)
def repasse_mes(request):
    competencia = _competencia_param(request)
    linhas = repasse.resumo_por_medico(competencia)
    fechamentos = [l["fechamento"] for l in linhas if l["fechamento"]]
    Status = FechamentoRepasse.Status
    context = {
        "em_area_repasse": True,
        "competencia": competencia,
        "anterior": somar_meses(competencia, -1),
        "proximo": somar_meses(competencia, 1),
        "linhas": linhas,
        "total": sum((l["total"] for l in linhas), Decimal(0)),
        "total_aberto": sum((l["em_aberto"] for l in linhas), Decimal(0)),
        "total_fechado": sum((f.valor_total for f in fechamentos if f.status == Status.FECHADO), Decimal(0)),
        "total_pago": sum((f.valor_total for f in fechamentos if f.status == Status.PAGO), Decimal(0)),
        "pendencias": repasse.pendencias(competencia),
        "previsoes": [
            {"competencia": mes, "total": repasse.previsao(mes)}
            for mes in (somar_meses(competencia, i) for i in range(4))
        ],
    }
    return render(request, "agendas/repasse.html", context)


def _itens_detalhe(medico, competencia):
    """Itens congelados (se o mês já foi fechado) ou calculados na hora."""
    fechamento = FechamentoRepasse.objects.filter(medico=medico, competencia=competencia).first()
    if not fechamento:
        itens = [
            dict(linha, agenda_numero=linha["agenda"].id)
            for linha in repasse.itens_do_mes(competencia, medico_id=medico.id)
        ]
        return None, itens

    itens = [
        {
            "agenda_numero": i.agenda_numero,
            "data": i.data_atendimento,
            "unidade": i.unidade_nome,
            "procedimento": i.procedimento_nome,
            "tipo_calculo": i.get_tipo_calculo_display(),
            "prazo": i.prazo_repasse_meses,
            "valor_base": i.valor_base,
            "quantidade": i.quantidade,
            "valor": i.valor,
            "fora_do_prazo": False,
        }
        for i in fechamento.itens.all()
    ]
    return fechamento, itens


@cargo_required(Cargo.ADMINISTRADOR)
def repasse_detalhe(request, medico_id):
    medico = get_object_or_404(Medico.objects.select_related("conta_bancaria"), pk=medico_id)
    competencia = _competencia_param(request)
    fechamento, itens = _itens_detalhe(medico, competencia)

    if request.GET.get("formato") == "csv":
        return _repasse_csv(medico, competencia, itens)

    context = {
        "em_area_repasse": True,
        "medico": medico,
        "competencia": competencia,
        "fechamento": fechamento,
        "itens": itens,
        "total": sum((i["valor"] for i in itens), Decimal(0)),
    }
    return render(request, "agendas/repasse_detalhe.html", context)


def _repasse_csv(medico, competencia, itens):
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="repasse_{competencia:%Y-%m}_medico_{medico.id}.csv"'
    resposta.write("﻿")  # BOM para o Excel abrir os acentos corretamente
    escritor = csv.writer(resposta, delimiter=";")
    escritor.writerow(
        ["Agenda", "Data", "Unidade", "Procedimento", "Cálculo", "Prazo (meses)", "Valor base", "Quantidade", "Valor"]
    )
    for i in itens:
        escritor.writerow(
            [
                i["agenda_numero"],
                f"{i['data']:%d/%m/%Y}",
                i["unidade"],
                i["procedimento"],
                i["tipo_calculo"],
                i["prazo"],
                str(i["valor_base"]).replace(".", ","),
                i["quantidade"],
                str(i["valor"]).replace(".", ","),
            ]
        )
    return resposta


@cargo_required(Cargo.ADMINISTRADOR)
def repasse_acao(request, medico_id):
    """Fechar, marcar como pago ou reabrir o repasse de um médico no mês."""
    medico = get_object_or_404(Medico, pk=medico_id)
    competencia = _competencia_param(request)
    destino = request.POST.get("voltar", "")
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        destino = f"{reverse('agendas:repasse')}?mes={competencia:%Y-%m}"
    if request.method != "POST":
        return redirect(destino)

    acao = request.POST.get("acao")
    try:
        if acao == "fechar":
            repasse.fechar(medico, competencia, request.user)
            messages.success(request, f"Repasse de {medico.nome} fechado.")
        elif acao in ("pagar", "reabrir"):
            fechamento = get_object_or_404(FechamentoRepasse, medico=medico, competencia=competencia)
            if acao == "pagar":
                repasse.marcar_pago(fechamento, request.user, request.POST.get("observacao", "").strip())
                messages.success(request, f"Repasse de {medico.nome} marcado como pago.")
            else:
                repasse.reabrir(fechamento)
                messages.success(request, f"Fechamento de {medico.nome} reaberto.")
    except ValueError as erro:
        messages.error(request, str(erro))
    return redirect(destino)
