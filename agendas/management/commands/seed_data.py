import datetime
import random

from django.core.management.base import BaseCommand
from django.db import transaction

from agendas.models import (
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

UNIDADES = [
    "Hospital de Olhos Central",
    "Clínica Visão Norte",
    "Clínica Visão Sul",
]

ESPECIALIDADES_SALA = ["Consultório Oftalmológico", "Centro Cirúrgico", "Sala de Exames"]

CONTAS = [
    dict(chave_pix="12345678900", tipo_pix="cpf", nome_banco="Banco do Brasil",
         numero_conta="12345-6", codigo_conta="001", agencia="1234", cnpj=""),
    dict(chave_pix="dr.silva@email.com", tipo_pix="email", nome_banco="Itaú",
         numero_conta="98765-4", codigo_conta="341", agencia="5678", cnpj=""),
    dict(chave_pix="11222333000144", tipo_pix="cnpj", nome_banco="Bradesco",
         numero_conta="55555-5", codigo_conta="237", agencia="4321", cnpj="11.222.333/0001-44"),
    dict(chave_pix="chave-aleatoria-abc123", tipo_pix="aleatoria", nome_banco="Nubank",
         numero_conta="11111-1", codigo_conta="260", agencia="0001", cnpj=""),
]

MEDICOS = [
    ("Dra. Ana Beatriz Ramos", "Catarata"),
    ("Dr. Carlos Eduardo Lima", "Retina"),
    ("Dra. Fernanda Torres", "Glaucoma"),
    ("Dr. Marcelo Andrade", "Cirurgia Refrativa"),
    ("Dra. Juliana Prado", "Oftalmopediatria"),
    ("Dr. Rafael Nogueira", "Catarata"),
    ("Dra. Patrícia Gomes", "Retina"),
]

PROCEDIMENTOS = [
    ("Consulta Oftalmológica", 250.00),
    ("Cirurgia de Catarata", 3500.00),
    ("Exame de Fundo de Olho", 180.00),
    ("Cirurgia Refrativa a Laser", 4200.00),
    ("Mapeamento de Retina", 320.00),
    ("Tonometria (Pressão Ocular)", 120.00),
]

CONCIERGES = ["Beatriz Souza", "João Pedro Alves", "Camila Ferreira", ""]


class Command(BaseCommand):
    help = "Popula o banco com dados fictícios para o protótipo Virtù."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sem-limpar",
            action="store_true",
            help="Não apaga os dados existentes antes de popular.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(42)

        if not options["sem_limpar"]:
            self.stdout.write("Limpando dados existentes...")
            ProcedimentoAgenda.objects.all().delete()
            Agenda.objects.all().delete()
            SalaHorario.objects.all().delete()
            Horario.objects.all().delete()
            Procedimento.objects.all().delete()
            UnidadeMedico.objects.all().delete()
            Medico.objects.all().delete()
            Sala.objects.all().delete()
            Unidade.objects.all().delete()
            ContaBancaria.objects.all().delete()

        unidades = [Unidade.objects.create(nome=nome) for nome in UNIDADES]
        self.stdout.write(f"Criadas {len(unidades)} unidades.")

        salas = []
        for unidade in unidades:
            for i in range(1, 4):
                sala = Sala.objects.create(
                    nome=f"Sala {i}",
                    especialidade=random.choice(ESPECIALIDADES_SALA),
                    unidade=unidade,
                )
                salas.append(sala)
        self.stdout.write(f"Criadas {len(salas)} salas.")

        contas = [ContaBancaria.objects.create(**dados) for dados in CONTAS]
        self.stdout.write(f"Criadas {len(contas)} contas bancárias.")

        medicos = []
        for nome, subespecialidade in MEDICOS:
            medico = Medico.objects.create(
                nome=nome,
                email=nome.split()[-1].lower() + "@virtuclinicas.com.br",
                telefone=f"(11) 9{random.randint(1000,9999)}-{random.randint(1000,9999)}",
                especialidade=f"Oftalmologia - {subespecialidade}",
                conta_bancaria=random.choice(contas),
            )
            for unidade in random.sample(unidades, k=random.choice([1, 2])):
                UnidadeMedico.objects.create(unidade=unidade, medico=medico)
            medicos.append(medico)
        self.stdout.write(f"Criados {len(medicos)} médicos.")

        procedimentos = []
        for unidade in unidades:
            for nome_proc, valor in PROCEDIMENTOS:
                procedimentos.append(
                    Procedimento.objects.create(
                        nome_procedimento=nome_proc,
                        valor_base=valor,
                        especialidade="Oftalmologia",
                        unidade=unidade,
                    )
                )
        self.stdout.write(f"Criados {len(procedimentos)} procedimentos.")

        hoje = datetime.date.today()
        inicio_semana = hoje - datetime.timedelta(days=hoje.weekday())
        dias = [inicio_semana + datetime.timedelta(days=i) for i in range(14)]  # 2 semanas

        turnos = [
            (datetime.time(8, 0), datetime.time(12, 0)),
            (datetime.time(13, 0), datetime.time(17, 0)),
        ]

        total_agendas = 0
        for dia in dias:
            if dia.weekday() == 6:  # pula domingo
                continue
            for unidade in unidades:
                salas_unidade = [s for s in salas if s.unidade_id == unidade.id]
                medicos_unidade = [m for m in medicos if unidade in m.unidades.all()]
                procedimentos_unidade = [p for p in procedimentos if p.unidade_id == unidade.id]

                for sala in random.sample(salas_unidade, k=random.choice([1, 2])):
                    inicio, fim = random.choice(turnos)
                    horario = Horario.objects.create(data=dia, horario_inicio=inicio, horario_fim=fim)
                    SalaHorario.objects.create(sala=sala, horario=horario)

                    # ~20% das agendas ficam sem médico alocado (vaga em aberto)
                    tem_medico = random.random() > 0.2 and medicos_unidade
                    medico_inicial = random.choice(medicos_unidade) if tem_medico else None

                    confirmado = random.random() > 0.35 if medico_inicial else False
                    tem_substituto = medico_inicial and random.random() < 0.15
                    medico_substituto = None
                    if tem_substituto:
                        outros = [m for m in medicos_unidade if m != medico_inicial]
                        if outros:
                            medico_substituto = random.choice(outros)

                    agenda = Agenda.objects.create(
                        concierge=random.choice(CONCIERGES),
                        tipo_calculo_pagamento=random.random() > 0.5,
                        valor_real=None,
                        confirmacao_medico=confirmado if not medico_substituto else True,
                        horario=horario,
                        medico_inicial=medico_inicial,
                        medico_atendido=medico_substituto or (medico_inicial if confirmado else None),
                    )

                    if medico_inicial and procedimentos_unidade:
                        for proc in random.sample(
                            procedimentos_unidade, k=random.choice([1, 1, 2])
                        ):
                            ProcedimentoAgenda.objects.create(
                                agenda=agenda,
                                procedimento=proc,
                                esperanca_pacientes=random.randint(1, 8),
                                real_pacientes=None,
                            )
                    total_agendas += 1

        self.stdout.write(self.style.SUCCESS(f"Criadas {total_agendas} agendas ao longo de 2 semanas."))
        self.stdout.write(self.style.SUCCESS("Seed concluído com sucesso."))
