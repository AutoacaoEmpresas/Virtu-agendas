import datetime


def somar_meses(dia, n):
    """Primeiro dia do mês que fica n meses depois (ou antes, se n < 0) do mês de `dia`."""
    mes_total = dia.month - 1 + n
    ano = dia.year + mes_total // 12
    mes = mes_total % 12 + 1
    return dia.replace(year=ano, month=mes, day=1)


def ultimo_dia_mes(primeiro_dia):
    return somar_meses(primeiro_dia, 1) - datetime.timedelta(days=1)


def parse_mes(value, default):
    """'AAAA-MM' -> date do dia 1 daquele mês."""
    if not value:
        return default
    try:
        return datetime.datetime.strptime(value, "%Y-%m").date()
    except ValueError:
        return default
