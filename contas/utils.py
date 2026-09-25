import random
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.utils import timezone

OTP_VALIDADE_MINUTOS = 5
OTP_MAX_TENTATIVAS = 5
SESSION_KEY = "otp_pendente"


def gerar_e_enviar_otp(request, usuario):
    codigo = f"{random.randint(0, 999999):06d}"
    request.session[SESSION_KEY] = {
        "user_id": usuario.pk,
        "hash": make_password(codigo),
        "expira": (timezone.now() + timedelta(minutes=OTP_VALIDADE_MINUTOS)).isoformat(),
        "tentativas": 0,
    }
    send_mail(
        subject="Seu código de verificação - Virtù",
        message=(
            f"Olá, {usuario.get_full_name() or usuario.username}!\n\n"
            f"Seu código de verificação é: {codigo}\n"
            f"Ele é válido por {OTP_VALIDADE_MINUTOS} minutos."
        ),
        from_email=None,
        recipient_list=[usuario.email],
    )


def limpar_otp_pendente(request):
    request.session.pop(SESSION_KEY, None)


def obter_otp_pendente(request):
    return request.session.get(SESSION_KEY)


def validar_otp(request, codigo):
    """Retorna (ok: bool, mensagem_erro: str|None)."""
    pendente = obter_otp_pendente(request)
    if not pendente:
        return False, "Nenhuma verificação em andamento. Faça login novamente."

    if timezone.now().isoformat() > pendente["expira"]:
        limpar_otp_pendente(request)
        return False, "Código expirado. Faça login novamente para receber um novo."

    if pendente["tentativas"] >= OTP_MAX_TENTATIVAS:
        limpar_otp_pendente(request)
        return False, "Número máximo de tentativas excedido. Faça login novamente."

    if not check_password(codigo, pendente["hash"]):
        pendente["tentativas"] += 1
        request.session[SESSION_KEY] = pendente
        return False, "Código incorreto."

    return True, None
