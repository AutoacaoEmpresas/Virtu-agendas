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
- **Procedimento**: pertence a uma unidade, tem `valor_base`, `tipo_calculo`
  ("por procedimento" = valor base cheio uma vez; "por paciente" = valor base
  × pacientes), `prazo_repasse_meses` (1 = paga no mês seguinte ao
  atendimento, 3 = paga 3 meses depois) e `medico_exclusivo` opcional
  (procedimentos especiais para exceções de um médico).
- **Horario**: data + faixa de horário, N:N com `Sala` (via `SalaHorario`,
  hoje sempre 1 sala por horário na prática); `turno` (Manhã/Tarde/Noite) é
  calculado a partir do horário de início.
- **Agenda**: entidade central — 1:1 com `Horario`, aponta para
  `medico_inicial` e `medico_atendido` (podem divergir quando há
  substituto), N:N com `Procedimento` via `ProcedimentoAgenda`
  (`esperanca_pacientes` / `real_pacientes` por procedimento).
  - Realização (`realizada`, `hora_chegada`, `hora_saida`, `realizada_em`,
    `realizada_por`): preenchida pela concierge; só agendas realizadas
    entram no repasse. (O antigo `tipo_calculo_pagamento` da agenda foi
    movido para `Procedimento.tipo_calculo` na migration `0006`.)
  - `valor_previsto` / `valor_real` são `@property` calculadas a partir dos
    procedimentos — nunca persistidas diretamente (adicionado no commit
    `ed49d16`, que removeu o campo antigo `valor_real` do banco via
    migration `0002_remove_agenda_valor_real`).

- **FechamentoRepasse** / **ItemRepasse**: fechamento mensal do repasse de
  um médico (`competencia` = dia 1 do mês de pagamento; status fechado →
  pago). Os itens congelam valor base, quantidade e valor no momento do
  fechamento.

## Repasse médico (`agendas/repasse.py`, tela `/repasse/`)

- O valor de cada `ProcedimentoAgenda` de uma agenda **realizada** vai para o
  `medico_atendido` e é pago no **mês do atendimento + prazo do
  procedimento** (ex.: atendimento em out/26 com prazo 3 → pago em jan/27).
- A tela abre no mês seguinte e mostra, por médico: valores de prazo 1 e 3,
  total, status (em aberto / fechado / pago) e PIX. Também lista agendas
  ainda não realizadas que afetam o mês e uma previsão dos próximos meses
  (usa pacientes esperados nas agendas não realizadas).
- **Fechar** congela os itens; agendas com itens fechados ficam travadas
  para edição. **Reabrir** só antes de pagar. **Marcar pago** grava data e
  usuário. Detalhe por médico com exportação CSV.
- Atendimento lançado depois que seu mês já foi fechado entra no próximo
  mês ainda não fechado do médico, marcado como "fora do prazo".

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
   - Valores previsto/real calculados conforme o tipo de cálculo de cada
     procedimento; na edição, bloco de realização (realizada, chegada e
     saída do médico).
   - Botões "Exportar relatório" e "Configurações" na tela inicial são só
     de fachada, sem funcionalidade.

## Dados de teste

`python manage.py seed_data` popula unidades, salas, contas bancárias,
médicos, procedimentos e agendas dos últimos 3 meses (a maioria já
realizada, para alimentar o repasse) até 2 semanas à frente de forma determinística
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
- Testes automatizados só cobrem o repasse (`agendas/tests.py`).
- Recorrência hoje só suporta frequência semanal (não diária/mensal).
- `admin.py` só tem registro básico dos models, sem `list_display`/
  `search_fields` customizados.
