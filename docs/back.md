# Virtù — Resumo do que já foi feito

> Snapshot em 2026-09-25, branch `dev-conde`. Este documento resume o estado
> atual do backend/projeto para retomar o trabalho rapidamente. Para detalhes
> de "como cada arquivo funciona", ver `GUIA_DO_PROJETO.md`; para instruções
> de setup, ver `README.md`.

## O que é o projeto

Protótipo em Django do **Virtù**, sistema de agendamento de procedimentos
oftalmológicos realizados por médicos em diferentes unidades de saúde.
Objetivo do protótipo: validar o modelo de dados e o fluxo das telas
principais (calendário, lista de agendamentos do dia, cadastro de agenda).
Sem autenticação, sem testes automatizados, banco padrão é SQLite local —
não tem preocupação de produção além do necessário para rodar num deploy de
demonstração (Render).

## Stack

- **Django 5.2** (`virtu_config/` = configuração do projeto, `agendas/` =
  única app).
- Banco: **SQLite** em desenvolvimento (`db.sqlite3`). Já existiu uma
  tentativa de migrar para MySQL/PostgreSQL (commits `715ac80` /
  `8acbffc`), mas foi revertida — o projeto segue em SQLite.
- Deploy: **Render**, via `build.sh` (`pip install` → `collectstatic` →
  `migrate` → `seed_data`), servido com **gunicorn** + **whitenoise** para
  estáticos. `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS` lidos de variáveis de
  ambiente em `settings.py`.
- Frontend: templates Django + Bootstrap (via CDN) + JavaScript puro
  (delegação de eventos em `main.js`, sem framework SPA). Fragmentos HTML
  via `fetch` para abrir modais (padrão "HTML-over-the-wire").

## Histórico de commits (branch dev-conde)

| Data | Commit | O que fez |
|---|---|---|
| 2026-09-03 | `47f5ef4` | Initial commit |
| 2026-09-03 | `caad235` | Primeiro protótipo funcional (models, views, templates, seed) |
| 2026-09-04 | `715ac80` / `8acbffc` | Tentativa de trocar SQLite por MySQL/Postgres — revertida |
| 2026-09-04 | `9cb63d1` | Ajustes para deploy no Render (`build.sh`, whitenoise, variáveis de ambiente) |
| 2026-09-09 | `8cd6587` | Reescrita grande de templates: views de **Dia / Semana / Mês / Ano** no calendário principal, novo `base.html`, CSS extenso, `GUIA_DO_PROJETO.md` |
| 2026-09-09 | `59a898d` | Recorrência semanal com **escolha do dia da semana** e intervalo (a cada 1 ou 2 semanas) no cadastro de agenda |
| 2026-09-18 | `ed49d16` | **Cálculo de procedimentos**: tipo de cálculo de pagamento (por procedimento vs. por paciente) refletido em `valor_previsto`/`valor_real`, ajustes no formulário e JS |

## Modelo de dados (`agendas/models.py`)

```
Unidade ──< Sala ──< SalaHorario >── Horario ── Agenda >── ProcedimentoAgenda >── Procedimento
   │                                              │
   └──< Procedimento                              ├── medico_inicial ─┐
                                                    ├── medico_atendido ┤→ Medico ──< UnidadeMedico >── Unidade
                                                                        │        └── conta_bancaria → ContaBancaria
```

- **Unidade**: clínica/hospital.
- **Sala**: pertence a uma unidade, tem especialidade.
- **ContaBancaria**: dados bancários/PIX de um médico.
- **Medico**: N:N com `Unidade` (via `UnidadeMedico`), 1 conta bancária.
- **Procedimento**: pertence a uma unidade, tem `valor_base`.
- **Horario**: data + faixa de horário, N:N com `Sala` (via `SalaHorario`,
  hoje sempre 1 sala por horário na prática); `turno` (Manhã/Tarde/Noite) é
  calculado a partir do horário de início.
- **Agenda**: entidade central — 1:1 com `Horario`, aponta para
  `medico_inicial` e `medico_atendido` (podem divergir quando há
  substituto), N:N com `Procedimento` via `ProcedimentoAgenda`
  (`esperanca_pacientes` / `real_pacientes` por procedimento).
  - `tipo_calculo_pagamento` (bool): `True` = "Por Procedimento" (soma
    `valor_base` cheio de cada procedimento), `False` = "Por Paciente"
    (multiplica `valor_base` pela quantidade de pacientes).
  - `valor_previsto` / `valor_real` são `@property` calculadas a partir dos
    procedimentos — nunca persistidas diretamente (adicionado no commit
    `ed49d16`, que removeu o campo antigo `valor_real` do banco via
    migration `0002_remove_agenda_valor_real`).

## Telas e fluxo (`agendas/views.py` + templates)

1. **Tela inicial (`home`)** — calendário com 4 visualizações alternáveis
   via `?view=`: **Dia**, **Semana** (padrão), **Mês** e **Ano**
   (`_contexto_dia`, `_contexto_semana`, `_contexto_mes`, `_contexto_ano`
   em `views.py`, cada uma com seu partial de template
   `_view_dia/_view_semana/_view_mes/_view_ano.html`). Tem:
   - Mini-calendário do mês na lateral, com dias marcados por cor de
     unidade.
   - Lista de "agendas abertas" (sem médico alocado), agrupada por dia com
     rótulos HOJE/AMANHÃ/dia da semana e destaque de urgência (≤15 dias).
   - Filtro por texto (médico, sala, especialidade, unidade) e por
     unidade, válido em todas as views.
2. **Modal "Lista de Agendamentos"** (`lista_agendamentos`, fragmento
   `_lista_agendamentos.html`) — aberto ao clicar num evento com médico
   alocado; tabela do dia com busca e ordenação (mais recentes/antigos),
   mostra procedimentos e total de pacientes esperados.
3. **Modal "Cadastro de Agenda"** (`cadastro_agenda` + `_salvar_agenda`,
   fragmento `_cadastro_agenda.html`) — cria ou edita uma agenda:
   - Unidade → sala (filtro client-side em `main.js`), médico inicial (com
     status confirmado/cancelado) e médico substituto.
   - Datas/horário, **recorrência semanal** com dia da semana escolhido e
     intervalo de 1 ou 2 semanas (gera várias `Agenda`/`Horario` de uma vez,
     dentro de uma transação atômica).
   - Linhas dinâmicas de procedimento (adicionar/remover), com
     `esperanca_pacientes` e `real_pacientes` por linha.
   - Tipo de cálculo de pagamento (por procedimento / por paciente),
     refletido nos valores previsto/real calculados no model.
   - Botões "Exportar relatório" e "Configurações" na tela inicial são só
     de fachada, sem funcionalidade.

## Dados de teste

`python manage.py seed_data` popula unidades, salas, contas bancárias,
médicos, procedimentos e ~2 semanas de agendas de forma determinística
(`random.seed(42)`). Pode ser rodado de novo a qualquer momento (apaga e
recria tudo, a menos que use `--sem-limpar`).

## O que falta / próximos passos conhecidos

(Ver seção 15 de `GUIA_DO_PROJETO.md` para a lista completa de exercícios
sugeridos.) Pontos ainda não resolvidos no projeto:

- Sem autenticação — qualquer pessoa com a URL acessa tudo, incluindo
  `/admin/`.
- Sem validação real de formulário (`_salvar_agenda` confia no
  `request.POST` bruto); candidato natural para migrar para
  `django.forms.ModelForm`.
- Sem testes automatizados (`agendas/tests.py` está vazio).
- Recorrência hoje só suporta frequência semanal (não diária/mensal).
- `admin.py` só tem registro básico dos models, sem `list_display`/
  `search_fields` customizados.
