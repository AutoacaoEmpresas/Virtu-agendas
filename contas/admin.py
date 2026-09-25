from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Virtù", {"fields": ("cargo", "unidades_permitidas")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Virtù", {"fields": ("email", "cargo", "unidades_permitidas")}),
    )
    filter_horizontal = BaseUserAdmin.filter_horizontal + ("unidades_permitidas",)
    list_display = ("username", "email", "cargo", "is_active")
    list_filter = BaseUserAdmin.list_filter + ("cargo",)
