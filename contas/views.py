from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.shortcuts import redirect, render

from .models import Usuario
from .utils import gerar_e_enviar_otp, limpar_otp_pendente, obter_otp_pendente, validar_otp


def login_view(request):
    if request.user.is_authenticated:
        return redirect("agendas:home")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        usuario = authenticate(request, username=username, password=password)

        if usuario is None:
            return render(request, "contas/login.html", {"erro": "Usuário ou senha inválidos."})

        if usuario.cargo == Usuario.Cargo.ADMINISTRADOR:
            if not usuario.email:
                messages.warning(
                    request,
                    "Cadastre um e-mail para este administrador para habilitar a verificação em duas etapas.",
                )
                login(request, usuario)
                return redirect("agendas:home")

            gerar_e_enviar_otp(request, usuario)
            return redirect("contas:verificar_otp")

        login(request, usuario)
        return redirect("agendas:home")

    return render(request, "contas/login.html")


def verificar_otp_view(request):
    pendente = obter_otp_pendente(request)
    if not pendente:
        return redirect("contas:login")

    if request.method == "POST":
        if "reenviar" in request.POST:
            usuario = Usuario.objects.get(pk=pendente["user_id"])
            gerar_e_enviar_otp(request, usuario)
            return render(request, "contas/otp.html", {"info": "Um novo código foi enviado."})

        codigo = request.POST.get("codigo", "").strip()
        ok, erro = validar_otp(request, codigo)
        if not ok:
            if obter_otp_pendente(request) is None:
                return redirect("contas:login")
            return render(request, "contas/otp.html", {"erro": erro})

        usuario = Usuario.objects.get(pk=pendente["user_id"])
        limpar_otp_pendente(request)
        login(request, usuario)
        return redirect("agendas:home")

    return render(request, "contas/otp.html")


class LogoutView(DjangoLogoutView):
    next_page = "contas:login"
