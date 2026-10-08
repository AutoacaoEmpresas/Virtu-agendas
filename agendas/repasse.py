"""Cálculo do repasse médico.

Regras:
- Só entram agendas realizadas, pagas ao médico que atendeu (Agenda.medico_atendido).
- Cada procedimento tem um prazo (Procedimento.prazo_repasse_meses): o repasse é pago no
  mês do atendimento + prazo. Ex.: atendimento em out/26 com prazo 3 -> pago em jan/27.
- Valor: por procedimento = valor base (uma vez); por paciente = valor base × pacientes reais.
- Ao fechar o mês de um médico, os itens são congelados em ItemRepasse. Um ProcedimentoAgenda
  só pode estar em um fechamento; o que foi realizado depois de um mês já fechado entra no
  próximo mês ainda não fechado daquele médico ("fora do prazo").
"""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import FechamentoRepasse, ItemRepasse, Procedimento, ProcedimentoAgenda
from .utils import somar_meses, ultimo_dia_mes

PRAZOS = [valor for valor, _ in Procedimento.PRAZO_REPASSE_CHOICES]


def mes_pagamento(data_atendimento, prazo):
    """Dia 1 do mês em que o atendimento é pago."""
    return somar_meses(data_atendimento, prazo)


def _base_qs():
    return ProcedimentoAgenda.objects.select_related(
        "procedimento",
        "agenda__horario",
        "agenda__medico_atendido__conta_bancaria",
    ).prefetch_related("agenda__horario__salas__unidade")


def _filtro_origem(qs, competencia):
    """Restringe aos ProcedimentoAgenda cujo atendimento é pago em `competencia`."""
    filtro = Q(pk__in=[])
    for prazo in PRAZOS:
        origem = somar_meses(competencia, -prazo)
        filtro |= Q(
            procedimento__prazo_repasse_meses=prazo,
            agenda__horario__data__range=[origem, ultimo_dia_mes(origem)],
        )
    return qs.filter(filtro)


def _linha(pa, quantidade, fora_do_prazo=False):
    agenda = pa.agenda
    proc = pa.procedimento
    salas = agenda.horario.salas.all()  # usa o prefetch (agenda.unidade faria uma query por linha)
    unidade = salas[0].unidade if salas else None
    return {
        "pa": pa,
        "agenda": agenda,
        "medico": agenda.medico_atendido,
        "data": agenda.horario.data,
        "unidade": unidade.nome if unidade else "-",
        "procedimento": proc.nome_procedimento,
        "tipo_calculo": proc.get_tipo_calculo_display(),
        "prazo": proc.prazo_repasse_meses,
        "valor_base": proc.valor_base,
        "quantidade": quantidade if proc.por_paciente else (1 if quantidade else 0),
        "valor": Decimal(proc.calcular_valor(quantidade)),
        "fora_do_prazo": fora_do_prazo,
    }


def itens_do_mes(competencia, medico_id=None):
    """Itens a pagar em `competencia` que ainda não estão em nenhum fechamento.

    Se o mês de origem de um item já foi fechado para o médico (item realizado/corrigido depois
    do fechamento), ele vai para o primeiro mês seguinte ainda não fechado ("fora do prazo").
    """
    qs = _base_qs().filter(
        agenda__realizada=True,
        agenda__medico_atendido__isnull=False,
        real_pacientes__gt=0,
        item_repasse__isnull=True,
    )
    if medico_id:
        qs = qs.filter(agenda__medico_atendido_id=medico_id)

    fechados = defaultdict(set)
    for medico, comp in FechamentoRepasse.objects.values_list("medico_id", "competencia"):
        fechados[medico].add(comp)

    linhas = [
        _linha(pa, pa.real_pacientes)
        for pa in _filtro_origem(qs, competencia)
        if competencia not in fechados[pa.agenda.medico_atendido_id]
    ]

    # Atendimentos cujo mês de pagamento original é anterior a `competencia`.
    for pa in qs.filter(agenda__horario__data__lt=somar_meses(competencia, -1)):
        original = mes_pagamento(pa.agenda.horario.data, pa.procedimento.prazo_repasse_meses)
        if original < competencia and _primeiro_mes_aberto(original, fechados[pa.agenda.medico_atendido_id]) == competencia:
            linhas.append(_linha(pa, pa.real_pacientes, fora_do_prazo=True))

    linhas.sort(key=lambda l: (l["medico"].nome, l["data"], l["procedimento"]))
    return linhas


def _primeiro_mes_aberto(mes, fechados):
    while mes in fechados:
        mes = somar_meses(mes, 1)
    return mes


def pendencias(competencia):
    """Agendas com médico que afetam `competencia`, mas ainda não foram marcadas como realizadas."""
    qs = _filtro_origem(
        _base_qs().filter(agenda__realizada=False, agenda__medico_atendido__isnull=False),
        competencia,
    )
    agendas = {}
    for pa in qs:
        agendas.setdefault(pa.agenda_id, pa.agenda)
    return sorted(agendas.values(), key=lambda a: (a.horario.data, a.horario.horario_inicio))


def previsao(competencia):
    """Total previsto para `competencia`: realizado (pacientes reais) + não realizado (esperados)."""
    fechamentos = FechamentoRepasse.objects.filter(competencia=competencia)
    qs = _filtro_origem(
        _base_qs()
        .filter(agenda__medico_atendido__isnull=False, item_repasse__isnull=True)
        .exclude(agenda__medico_atendido__in=fechamentos.values("medico")),
        competencia,
    )
    total = sum((f.valor_total for f in fechamentos), Decimal(0))
    for pa in qs:
        quantidade = pa.real_pacientes if pa.agenda.realizada else pa.esperanca_pacientes
        total += Decimal(pa.procedimento.calcular_valor(quantidade))
    return total


def resumo_por_medico(competencia):
    """Uma linha por médico com valores em aberto (calculados) e/ou fechados (congelados)."""
    medicos = {}

    def linha_medico(medico):
        return medicos.setdefault(
            medico.id,
            {
                "medico": medico,
                "prazo_1": Decimal(0),
                "prazo_3": Decimal(0),
                "em_aberto": Decimal(0),
                "qtd_itens": 0,
                "fora_do_prazo": 0,
                "fechamento": None,
            },
        )

    for item in itens_do_mes(competencia):
        linha = linha_medico(item["medico"])
        linha[f"prazo_{item['prazo']}"] += item["valor"]
        linha["em_aberto"] += item["valor"]
        linha["qtd_itens"] += 1
        linha["fora_do_prazo"] += item["fora_do_prazo"]

    fechamentos = FechamentoRepasse.objects.select_related("medico__conta_bancaria").filter(competencia=competencia)
    for fechamento in fechamentos:
        linha = linha_medico(fechamento.medico)
        linha["fechamento"] = fechamento
        for prazo, valor in _totais_por_prazo(fechamento).items():
            linha[f"prazo_{prazo}"] += valor

    for linha in medicos.values():
        fechado = linha["fechamento"].valor_total if linha["fechamento"] else Decimal(0)
        linha["total"] = linha["em_aberto"] + fechado

    return sorted(medicos.values(), key=lambda l: l["medico"].nome)


def _totais_por_prazo(fechamento):
    totais = defaultdict(Decimal)
    for item in fechamento.itens.all():
        totais[item.prazo_repasse_meses] += item.valor
    return totais


@transaction.atomic
def fechar(medico, competencia, usuario):
    """Congela os itens em aberto do médico no mês."""
    if FechamentoRepasse.objects.filter(medico=medico, competencia=competencia).exists():
        raise ValueError("O repasse deste médico neste mês já foi fechado.")
    linhas = itens_do_mes(competencia, medico_id=medico.id)
    if not linhas:
        raise ValueError("Não há itens a fechar para este médico neste mês.")

    fechamento = FechamentoRepasse.objects.create(medico=medico, competencia=competencia, fechado_por=usuario)
    for linha in linhas:
        ItemRepasse.objects.create(
            fechamento=fechamento,
            procedimento_agenda=linha["pa"],
            agenda_numero=linha["agenda"].id,
            data_atendimento=linha["data"],
            unidade_nome=linha["unidade"],
            procedimento_nome=linha["procedimento"],
            tipo_calculo=linha["pa"].procedimento.tipo_calculo,
            prazo_repasse_meses=linha["prazo"],
            valor_base=linha["valor_base"],
            quantidade=linha["quantidade"],
            valor=linha["valor"],
        )
    fechamento.valor_total = sum((linha["valor"] for linha in linhas), Decimal(0))
    fechamento.save(update_fields=["valor_total"])
    return fechamento


def marcar_pago(fechamento, usuario, observacao=""):
    fechamento.status = FechamentoRepasse.Status.PAGO
    fechamento.pago_em = timezone.now()
    fechamento.pago_por = usuario
    if observacao:
        fechamento.observacao = observacao
    fechamento.save()


def reabrir(fechamento):
    """Desfaz um fechamento ainda não pago: os itens voltam a ser calculados."""
    if fechamento.status == FechamentoRepasse.Status.PAGO:
        raise ValueError("Repasse pago não pode ser reaberto.")
    fechamento.delete()


def agenda_travada(agenda):
    """True se algum procedimento da agenda já está em um fechamento de repasse."""
    return ItemRepasse.objects.filter(procedimento_agenda__agenda=agenda).exists()
