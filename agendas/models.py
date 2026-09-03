import datetime

from django.db import models


class Unidade(models.Model):
    nome = models.CharField(max_length=150)

    class Meta:
        verbose_name = "Unidade"
        verbose_name_plural = "Unidades"

    def __str__(self):
        return self.nome


class Sala(models.Model):
    nome = models.CharField(max_length=100)
    especialidade = models.CharField(max_length=100)
    unidade = models.ForeignKey(Unidade, on_delete=models.CASCADE, related_name="salas")

    class Meta:
        verbose_name = "Sala"
        verbose_name_plural = "Salas"

    def __str__(self):
        return f"{self.nome} ({self.unidade.nome})"


class ContaBancaria(models.Model):
    TIPO_PIX_CHOICES = [
        ("cpf", "CPF"),
        ("cnpj", "CNPJ"),
        ("email", "E-mail"),
        ("telefone", "Telefone"),
        ("aleatoria", "Chave Aleatória"),
    ]

    chave_pix = models.CharField(max_length=150)
    tipo_pix = models.CharField(max_length=20, choices=TIPO_PIX_CHOICES)
    nome_banco = models.CharField(max_length=100)
    numero_conta = models.CharField(max_length=30)
    codigo_conta = models.CharField(max_length=30, blank=True)
    agencia = models.CharField(max_length=20)
    cnpj = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "Conta Bancária"
        verbose_name_plural = "Contas Bancárias"

    def __str__(self):
        return f"{self.nome_banco} - {self.numero_conta}"


class Medico(models.Model):
    nome = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    especialidade = models.CharField(max_length=100)
    conta_bancaria = models.ForeignKey(
        ContaBancaria, on_delete=models.SET_NULL, null=True, blank=True, related_name="medicos"
    )
    unidades = models.ManyToManyField(Unidade, through="UnidadeMedico", related_name="medicos")

    class Meta:
        verbose_name = "Médico"
        verbose_name_plural = "Médicos"

    def __str__(self):
        return self.nome


class UnidadeMedico(models.Model):
    unidade = models.ForeignKey(Unidade, on_delete=models.CASCADE)
    medico = models.ForeignKey(Medico, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Unidade x Médico"
        verbose_name_plural = "Unidade x Médico"
        unique_together = ("unidade", "medico")

    def __str__(self):
        return f"{self.medico.nome} @ {self.unidade.nome}"


class Procedimento(models.Model):
    nome_procedimento = models.CharField(max_length=150)
    valor_base = models.DecimalField(max_digits=10, decimal_places=2)
    especialidade = models.CharField(max_length=100)
    unidade = models.ForeignKey(Unidade, on_delete=models.CASCADE, related_name="procedimentos")

    class Meta:
        verbose_name = "Procedimento"
        verbose_name_plural = "Procedimentos"

    def __str__(self):
        return self.nome_procedimento


class Horario(models.Model):
    data = models.DateField()
    horario_inicio = models.TimeField()
    horario_fim = models.TimeField()
    salas = models.ManyToManyField(Sala, through="SalaHorario", related_name="horarios")

    class Meta:
        verbose_name = "Horário"
        verbose_name_plural = "Horários"
        ordering = ["data", "horario_inicio"]

    def __str__(self):
        return f"{self.data} {self.horario_inicio}-{self.horario_fim}"

    @property
    def turno(self):
        if self.horario_inicio < datetime.time(12, 0):
            return "Manhã"
        elif self.horario_inicio < datetime.time(18, 0):
            return "Tarde"
        return "Noite"


class SalaHorario(models.Model):
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE)
    horario = models.ForeignKey(Horario, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Sala x Horário"
        verbose_name_plural = "Sala x Horário"
        unique_together = ("sala", "horario")

    def __str__(self):
        return f"{self.sala.nome} @ {self.horario}"


class Agenda(models.Model):
    concierge = models.CharField(max_length=150, blank=True)
    tipo_calculo_pagamento = models.BooleanField(
        default=True, help_text="True = Por Procedimento, False = Por Paciente"
    )
    valor_real = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    confirmacao_medico = models.BooleanField(default=False)
    horario = models.OneToOneField(Horario, on_delete=models.CASCADE, related_name="agenda")
    medico_inicial = models.ForeignKey(
        Medico, on_delete=models.SET_NULL, null=True, blank=True, related_name="agendas_iniciais"
    )
    medico_atendido = models.ForeignKey(
        Medico, on_delete=models.SET_NULL, null=True, blank=True, related_name="agendas_atendidas"
    )
    procedimentos = models.ManyToManyField(
        Procedimento, through="ProcedimentoAgenda", related_name="agendas"
    )

    class Meta:
        verbose_name = "Agenda"
        verbose_name_plural = "Agendas"

    def __str__(self):
        medico = self.medico_inicial.nome if self.medico_inicial else "Sem médico"
        return f"Agenda #{self.id} - {medico} - {self.horario}"

    @property
    def sala(self):
        return self.horario.salas.first()

    @property
    def unidade(self):
        sala = self.sala
        return sala.unidade if sala else None

    @property
    def valor_previsto(self):
        total = 0
        for pa in self.procedimentoagenda_set.select_related("procedimento").all():
            total += pa.procedimento.valor_base * pa.esperanca_pacientes
        return total


class ProcedimentoAgenda(models.Model):
    agenda = models.ForeignKey(Agenda, on_delete=models.CASCADE)
    procedimento = models.ForeignKey(Procedimento, on_delete=models.CASCADE)
    esperanca_pacientes = models.PositiveIntegerField(default=1)
    real_pacientes = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Procedimento da Agenda"
        verbose_name_plural = "Procedimentos da Agenda"

    def __str__(self):
        return f"{self.procedimento.nome_procedimento} ({self.agenda_id})"
