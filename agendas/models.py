import datetime

from django.conf import settings
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
    class TipoCalculo(models.TextChoices):
        PROCEDIMENTO = "procedimento", "Por procedimento"
        PACIENTE = "paciente", "Por paciente"

    PRAZO_REPASSE_CHOICES = [(1, "Mês seguinte"), (3, "Em 3 meses")]

    nome_procedimento = models.CharField(max_length=150)
    valor_base = models.DecimalField(max_digits=10, decimal_places=2)
    especialidade = models.CharField(max_length=100)
    unidade = models.ForeignKey(Unidade, on_delete=models.CASCADE, related_name="procedimentos")
    tipo_calculo = models.CharField(
        max_length=20, choices=TipoCalculo.choices, default=TipoCalculo.PROCEDIMENTO,
        help_text="Por procedimento: o médico recebe o valor base uma vez. Por paciente: valor base × pacientes.",
    )
    prazo_repasse_meses = models.PositiveSmallIntegerField(
        choices=PRAZO_REPASSE_CHOICES, default=1,
        help_text="Meses após o mês do atendimento em que o médico recebe.",
    )
    # Procedimentos especiais (exceções de valor/regra) que só valem para um médico.
    medico_exclusivo = models.ForeignKey(
        Medico, on_delete=models.CASCADE, null=True, blank=True, related_name="procedimentos_exclusivos"
    )

    class Meta:
        verbose_name = "Procedimento"
        verbose_name_plural = "Procedimentos"

    def __str__(self):
        return self.nome_procedimento

    @property
    def por_paciente(self):
        return self.tipo_calculo == self.TipoCalculo.PACIENTE

    def calcular_valor(self, pacientes):
        """Valor do médico para `pacientes` atendidos (0/None = não realizado)."""
        if not pacientes:
            return 0
        return self.valor_base * pacientes if self.por_paciente else self.valor_base


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


class Recorrencia(models.Model):
    """Agrupa as agendas geradas de uma vez por uma recorrência semanal."""

    data_inicial = models.DateField()
    data_final = models.DateField()
    dia_semana = models.PositiveSmallIntegerField(help_text="0 = Segunda ... 6 = Domingo")
    intervalo_semanas = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = "Recorrência"
        verbose_name_plural = "Recorrências"

    def __str__(self):
        return f"Recorrência #{self.id} ({self.data_inicial} a {self.data_final})"


class Agenda(models.Model):
    class StatusMedicoInicial(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        CONFIRMADO = "confirmado", "Confirmado"
        CANCELADO = "cancelado", "Cancelado"

    concierge = models.CharField(max_length=150, blank=True)
    status_medico_inicial = models.CharField(
        max_length=20, choices=StatusMedicoInicial.choices, default=StatusMedicoInicial.PENDENTE
    )
    recorrencia = models.ForeignKey(
        Recorrencia, on_delete=models.SET_NULL, null=True, blank=True, related_name="agendas"
    )
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
    # Realização (preenchida pela concierge): só agendas realizadas entram no repasse.
    realizada = models.BooleanField(default=False)
    hora_chegada = models.TimeField(null=True, blank=True)
    hora_saida = models.TimeField(null=True, blank=True)
    realizada_em = models.DateTimeField(null=True, blank=True)
    realizada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "Agenda"
        verbose_name_plural = "Agendas"

    def __str__(self):
        medico = self.medico_inicial.nome if self.medico_inicial else "Sem médico"
        return f"Agenda #{self.id} - {medico} - {self.horario}"

    @property
    def status(self):
        """Status geral da agenda: 'confirmado', 'cancelado' (sem substituto) ou 'esperando'."""
        if self.confirmacao_medico:
            return "confirmado"
        if self.status_medico_inicial == self.StatusMedicoInicial.CANCELADO and not self.medico_atendido_id:
            return "cancelado"
        return "esperando"

    @property
    def sala(self):
        return self.horario.salas.first()

    @property
    def unidade(self):
        sala = self.sala
        return sala.unidade if sala else None

    @property
    def valor_previsto(self):
        return sum(pa.valor_previsto for pa in self.procedimentoagenda_set.select_related("procedimento"))

    @property
    def valor_real(self):
        return sum(pa.valor_real for pa in self.procedimentoagenda_set.select_related("procedimento"))


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

    @property
    def valor_previsto(self):
        return self.procedimento.calcular_valor(self.esperanca_pacientes)

    @property
    def valor_real(self):
        return self.procedimento.calcular_valor(self.real_pacientes)


class LogAgenda(models.Model):
    """Histórico de alterações de agendas: uma linha por ação salva (cadastro, modificação, exclusão)."""

    class Acao(models.TextChoices):
        CADASTRO = "cadastro", "Cadastro"
        MODIFICACAO = "modificacao", "Modificação"
        EXCLUSAO = "exclusao", "Exclusão"

    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="logs_agenda"
    )
    # Cópias de texto para o histórico continuar legível mesmo se o usuário/agenda forem excluídos.
    usuario_nome = models.CharField(max_length=150)
    usuario_cargo = models.CharField(max_length=50, blank=True)
    acao = models.CharField(max_length=20, choices=Acao.choices)
    agenda_numero = models.PositiveIntegerField(null=True, blank=True)
    unidade = models.ForeignKey(Unidade, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    resumo = models.CharField(max_length=255)
    alteracoes = models.JSONField(default=list, help_text='Lista de {"campo", "antes", "depois"}')

    class Meta:
        verbose_name = "Histórico de Agenda"
        verbose_name_plural = "Histórico de Agendas"
        ordering = ["-criado_em", "-id"]

    def __str__(self):
        return f"{self.get_acao_display()} - Agenda #{self.agenda_numero} por {self.usuario_nome}"


class FechamentoRepasse(models.Model):
    """Repasse de um médico em um mês de pagamento (competência).

    Ao fechar, os valores são congelados em ItemRepasse: mudanças posteriores em procedimentos
    ou agendas não alteram o que já foi fechado/pago.
    """

    class Status(models.TextChoices):
        FECHADO = "fechado", "Fechado"
        PAGO = "pago", "Pago"

    medico = models.ForeignKey(Medico, on_delete=models.PROTECT, related_name="fechamentos_repasse")
    competencia = models.DateField(help_text="Dia 1 do mês em que o repasse é pago.")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.FECHADO)
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fechado_em = models.DateTimeField(auto_now_add=True)
    fechado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    pago_em = models.DateTimeField(null=True, blank=True)
    pago_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    observacao = models.TextField(blank=True)

    class Meta:
        verbose_name = "Fechamento de Repasse"
        verbose_name_plural = "Fechamentos de Repasse"
        ordering = ["-competencia", "medico__nome"]
        constraints = [
            models.UniqueConstraint(fields=["medico", "competencia"], name="unico_fechamento_medico_mes")
        ]

    def __str__(self):
        return f"Repasse {self.medico.nome} - {self.competencia:%m/%Y} ({self.get_status_display()})"


class ItemRepasse(models.Model):
    """Retrato congelado de um ProcedimentoAgenda dentro de um fechamento."""

    fechamento = models.ForeignKey(FechamentoRepasse, on_delete=models.CASCADE, related_name="itens")
    # SET_NULL: se a agenda for excluída depois, o item pago continua no histórico.
    procedimento_agenda = models.OneToOneField(
        ProcedimentoAgenda, on_delete=models.SET_NULL, null=True, blank=True, related_name="item_repasse"
    )
    agenda_numero = models.PositiveIntegerField(null=True, blank=True)
    data_atendimento = models.DateField()
    unidade_nome = models.CharField(max_length=150, blank=True)
    procedimento_nome = models.CharField(max_length=150)
    tipo_calculo = models.CharField(max_length=20, choices=Procedimento.TipoCalculo.choices)
    prazo_repasse_meses = models.PositiveSmallIntegerField()
    valor_base = models.DecimalField(max_digits=10, decimal_places=2)
    quantidade = models.PositiveIntegerField()
    valor = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Item de Repasse"
        verbose_name_plural = "Itens de Repasse"
        ordering = ["data_atendimento", "id"]

    def __str__(self):
        return f"{self.procedimento_nome} ({self.data_atendimento:%d/%m/%Y}) - R$ {self.valor}"
