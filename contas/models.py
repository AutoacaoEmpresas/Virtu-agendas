from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class Usuario(AbstractUser):
    class Cargo(models.TextChoices):
        ADMINISTRADOR = "administrador", "Administrador"
        AGENDAMENTO = "agendamento", "Agendamento"
        CONCIERGE = "concierge", "Concierge"

    cargo = models.CharField(max_length=20, choices=Cargo.choices, default=Cargo.ADMINISTRADOR)
    unidades_permitidas = models.ManyToManyField(
        "agendas.Unidade",
        blank=True,
        related_name="usuarios_permitidos",
        verbose_name="Unidades permitidas",
        help_text="Ignorado para o cargo Administrador (que vê tudo).",
    )

    REQUIRED_FIELDS = ["email"]

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

    def save(self, *args, **kwargs):
        eh_admin = self.cargo == self.Cargo.ADMINISTRADOR
        self.is_staff = eh_admin
        self.is_superuser = eh_admin
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.cargo == self.Cargo.ADMINISTRADOR and not self.email:
            raise ValidationError(
                {"email": "Administrador precisa de um e-mail para receber o código de verificação (OTP)."}
            )

    @property
    def is_administrador(self):
        return self.cargo == self.Cargo.ADMINISTRADOR

    @property
    def is_agendamento(self):
        return self.cargo == self.Cargo.AGENDAMENTO

    @property
    def is_concierge(self):
        return self.cargo == self.Cargo.CONCIERGE

    def unidades_ids(self):
        """None = sem restrição (Administrador). Caso contrário, set de ids permitidos."""
        if self.is_administrador:
            return None
        return set(self.unidades_permitidas.values_list("id", flat=True))
