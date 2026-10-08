import datetime
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from contas.models import Usuario

from . import repasse
from .models import (
    Agenda,
    FechamentoRepasse,
    Horario,
    Medico,
    Procedimento,
    ProcedimentoAgenda,
    Sala,
    SalaHorario,
    Unidade,
)

OUT = datetime.date(2026, 10, 1)
NOV = datetime.date(2026, 11, 1)
JAN = datetime.date(2027, 1, 1)


class RepasseTestCase(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user("admin", password="x", cargo=Usuario.Cargo.ADMINISTRADOR)
        self.unidade = Unidade.objects.create(nome="Unidade")
        self.sala = Sala.objects.create(nome="Sala 1", especialidade="-", unidade=self.unidade)
        self.medico = Medico.objects.create(nome="Dra. Ana", especialidade="-")
        self.outro_medico = Medico.objects.create(nome="Dr. Bruno", especialidade="-")
        self.consulta = self._procedimento("Consulta", "100.00", Procedimento.TipoCalculo.PACIENTE, 1)
        self.cirurgia = self._procedimento("Cirurgia", "1000.00", Procedimento.TipoCalculo.PROCEDIMENTO, 3)

    def _procedimento(self, nome, valor, tipo, prazo, **extra):
        return Procedimento.objects.create(
            nome_procedimento=nome, valor_base=Decimal(valor), especialidade="-", unidade=self.unidade,
            tipo_calculo=tipo, prazo_repasse_meses=prazo, **extra,
        )

    def _agenda(self, data, procedimentos, realizada=True, medico=None):
        """procedimentos: lista de (procedimento, pacientes_reais)."""
        horario = Horario.objects.create(data=data, horario_inicio="08:00", horario_fim="12:00")
        SalaHorario.objects.create(sala=self.sala, horario=horario)
        medico = medico or self.medico
        agenda = Agenda.objects.create(
            horario=horario, medico_inicial=medico, medico_atendido=medico,
            status_medico_inicial="confirmado", confirmacao_medico=True, realizada=realizada,
        )
        for proc, reais in procedimentos:
            ProcedimentoAgenda.objects.create(agenda=agenda, procedimento=proc, esperanca_pacientes=5,
                                              real_pacientes=reais)
        return agenda

    def _total(self, competencia, medico=None):
        return sum(i["valor"] for i in repasse.itens_do_mes(competencia, medico_id=medico and medico.id))


class CalculoTests(RepasseTestCase):
    def test_mes_pagamento_vira_o_ano(self):
        self.assertEqual(repasse.mes_pagamento(datetime.date(2026, 10, 15), 3), JAN)
        self.assertEqual(repasse.mes_pagamento(datetime.date(2026, 10, 31), 1), NOV)

    def test_por_paciente_e_por_procedimento(self):
        self.assertEqual(self.consulta.calcular_valor(4), Decimal("400.00"))
        self.assertEqual(self.cirurgia.calcular_valor(4), Decimal("1000.00"))
        self.assertEqual(self.cirurgia.calcular_valor(0), 0)

    def test_prazos_caem_em_meses_diferentes(self):
        self._agenda(datetime.date(2026, 10, 15), [(self.consulta, 3), (self.cirurgia, 1)])
        self.assertEqual(self._total(OUT), 0)
        self.assertEqual(self._total(NOV), Decimal("300.00"))
        self.assertEqual(self._total(JAN), Decimal("1000.00"))

    def test_agenda_nao_realizada_fica_de_fora_e_vira_pendencia(self):
        agenda = self._agenda(datetime.date(2026, 10, 15), [(self.consulta, 3)], realizada=False)
        self.assertEqual(self._total(NOV), 0)
        self.assertEqual(repasse.pendencias(NOV), [agenda])

    def test_previsao_usa_pacientes_esperados_quando_nao_realizada(self):
        self._agenda(datetime.date(2026, 10, 15), [(self.consulta, None)], realizada=False)
        self.assertEqual(repasse.previsao(NOV), Decimal("500.00"))

    def test_pago_ao_medico_que_atendeu(self):
        self._agenda(datetime.date(2026, 10, 15), [(self.consulta, 2)], medico=self.outro_medico)
        self.assertEqual(self._total(NOV, self.medico), 0)
        self.assertEqual(self._total(NOV, self.outro_medico), Decimal("200.00"))

    def test_resumo_por_medico(self):
        self._agenda(datetime.date(2026, 10, 15), [(self.consulta, 2)])
        self._agenda(datetime.date(2026, 8, 10), [(self.cirurgia, 1)])
        [linha] = repasse.resumo_por_medico(NOV)
        self.assertEqual(linha["prazo_1"], Decimal("200.00"))
        self.assertEqual(linha["prazo_3"], Decimal("1000.00"))
        self.assertEqual(linha["total"], Decimal("1200.00"))


class FechamentoTests(RepasseTestCase):
    def test_fechar_congela_valores(self):
        self._agenda(datetime.date(2026, 10, 15), [(self.consulta, 3)])
        fechamento = repasse.fechar(self.medico, NOV, self.admin)
        self.assertEqual(fechamento.valor_total, Decimal("300.00"))

        self.consulta.valor_base = Decimal("999.00")
        self.consulta.save()
        [linha] = repasse.resumo_por_medico(NOV)
        self.assertEqual(linha["total"], Decimal("300.00"))
        self.assertEqual(self._total(NOV), 0)  # nada mais em aberto

    def test_nao_fecha_duas_vezes(self):
        self._agenda(datetime.date(2026, 10, 15), [(self.consulta, 3)])
        repasse.fechar(self.medico, NOV, self.admin)
        with self.assertRaises(ValueError):
            repasse.fechar(self.medico, NOV, self.admin)

    def test_lancamento_atrasado_vai_para_proximo_mes_aberto(self):
        self._agenda(datetime.date(2026, 10, 15), [(self.consulta, 3)])
        repasse.fechar(self.medico, NOV, self.admin)
        # Agenda de outubro realizada só depois do fechamento de novembro.
        self._agenda(datetime.date(2026, 10, 20), [(self.consulta, 1)])

        self.assertEqual(self._total(NOV), 0)
        [item] = repasse.itens_do_mes(datetime.date(2026, 12, 1))
        self.assertTrue(item["fora_do_prazo"])
        self.assertEqual(item["valor"], Decimal("100.00"))

    def test_pagar_e_reabrir(self):
        self._agenda(datetime.date(2026, 10, 15), [(self.consulta, 3)])
        fechamento = repasse.fechar(self.medico, NOV, self.admin)
        repasse.reabrir(fechamento)
        self.assertFalse(FechamentoRepasse.objects.exists())

        fechamento = repasse.fechar(self.medico, NOV, self.admin)
        repasse.marcar_pago(fechamento, self.admin)
        self.assertEqual(fechamento.status, FechamentoRepasse.Status.PAGO)
        with self.assertRaises(ValueError):
            repasse.reabrir(fechamento)

    def test_agenda_fechada_fica_travada(self):
        agenda = self._agenda(datetime.date(2026, 10, 15), [(self.consulta, 3)])
        repasse.fechar(self.medico, NOV, self.admin)
        self.assertTrue(repasse.agenda_travada(agenda))

        self.client.force_login(self.admin)
        url = reverse("agendas:cadastro_agenda_editar", args=[agenda.id])
        self.client.post(url, {"sala": self.sala.id, "data_inicial": "2026-10-15",
                               "procedimento[]": [self.consulta.id], "real_pacientes[]": ["9"]})
        self.assertEqual(ProcedimentoAgenda.objects.get(agenda=agenda).real_pacientes, 3)


# Nos testes não há collectstatic: usa o storage simples em vez do manifest do whitenoise.
@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class TelasTests(RepasseTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def test_tela_do_mes_e_detalhe(self):
        self._agenda(datetime.date(2026, 10, 15), [(self.consulta, 3)])
        resposta = self.client.get(reverse("agendas:repasse"), {"mes": "2026-11"})
        self.assertContains(resposta, "Dra. Ana")
        self.assertContains(resposta, "300,00")

        detalhe = reverse("agendas:repasse_detalhe", args=[self.medico.id])
        self.assertContains(self.client.get(detalhe, {"mes": "2026-11"}), "Consulta")
        csv = self.client.get(detalhe, {"mes": "2026-11", "formato": "csv"})
        self.assertIn("300,00", csv.content.decode("utf-8"))

    def test_acoes(self):
        self._agenda(datetime.date(2026, 10, 15), [(self.consulta, 3)])
        url = reverse("agendas:repasse_acao", args=[self.medico.id])
        self.client.post(url, {"mes": "2026-11", "acao": "fechar"})
        self.client.post(url, {"mes": "2026-11", "acao": "pagar", "observacao": "PIX enviado"})
        fechamento = FechamentoRepasse.objects.get()
        self.assertEqual(fechamento.status, FechamentoRepasse.Status.PAGO)
        self.assertEqual(fechamento.observacao, "PIX enviado")

    def test_procedimento_exclusivo_de_outro_medico_bloqueia_salvar(self):
        especial = self._procedimento("Especial Bruno", "50.00", Procedimento.TipoCalculo.PACIENTE, 1,
                                      medico_exclusivo=self.outro_medico)
        self.client.post(reverse("agendas:cadastro_agenda_nova"), {
            "sala": self.sala.id, "data_inicial": "2026-10-15", "medico_inicial": self.medico.id,
            "medico_inicial_status": "confirmado", "procedimento[]": [especial.id],
            "esperanca_pacientes[]": ["1"],
        })
        self.assertFalse(Agenda.objects.exists())

    def test_somente_admin(self):
        concierge = Usuario.objects.create_user("c", password="x", cargo=Usuario.Cargo.CONCIERGE)
        self.client.force_login(concierge)
        self.assertEqual(self.client.get(reverse("agendas:repasse")).status_code, 403)
