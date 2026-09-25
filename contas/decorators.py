from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def cargo_required(*cargos):
    """Restringe a view aos cargos informados (ex.: Usuario.Cargo.ADMINISTRADOR)."""

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.cargo not in cargos:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
