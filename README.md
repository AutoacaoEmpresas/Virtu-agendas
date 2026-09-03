# Virtù — Protótipo

Protótipo funcional em Django do sistema Virtù: ferramenta de agendamento de
procedimentos oftalmológicos realizados por médicos em diferentes unidades de
saúde. Objetivo: validar o modelo de dados e o fluxo das 3 telas principais
(tela inicial com calendário, lista de agendamentos do dia e cadastro de
agenda). Não possui autenticação, testes automatizados ou preocupação com
produção — é apenas para rodar localmente com dados fictícios.

## Como rodar

```bash
# 1. Criar e ativar um ambiente virtual
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Aplicar as migrations (cria o banco SQLite)
python manage.py migrate

# 4. Popular o banco com dados fictícios (unidades, salas, médicos,
#    contas bancárias, procedimentos e ~2 semanas de agendas)
python manage.py seed_data

# 5. Subir o servidor de desenvolvimento
python manage.py runserver
```

Acesse http://127.0.0.1:8000/ para a tela inicial.

O admin do Django (http://127.0.0.1:8000/admin/) também está habilitado para
inspecionar os dados diretamente — crie um superusuário com
`python manage.py createsuperuser` se quiser usá-lo (não é necessário para o
fluxo principal do protótipo).

Para reiniciar os dados fictícios a qualquer momento, rode `python manage.py
seed_data` novamente (ele apaga e recria tudo).

## Estrutura

- `virtu_config/` — configuração do projeto Django (settings, urls raiz).
- `agendas/` — app principal:
  - `models.py` — modelo de dados (Unidade, Sala, ContaBancaria, Medico,
    Procedimento, Horario, Agenda, ProcedimentoAgenda e tabelas associativas).
  - `views.py` — tela inicial (calendário semanal + menu lateral) e os dois
    modais (Lista de Agendamentos e Cadastro de Agenda).
  - `management/commands/seed_data.py` — comando de seed.
  - `templates/agendas/` — templates das telas e dos fragmentos dos modais.
  - `static/agendas/` — CSS e JS (abertura/fechamento dos modais via fetch,
    filtro de sala por unidade, linhas dinâmicas de procedimento).

## Fluxo das telas

1. **Tela inicial**: menu lateral com mini-calendário do mês (dias com agenda
   marcados) e lista de "agendas abertas" (sem médico alocado) agrupada por
   dia. Área principal com calendário semanal, filtro por texto e por
   unidade. Eventos são coloridos por unidade e mostram sala + médico.
2. Clicar num evento **com médico alocado** abre o modal **Lista de
   Agendamentos** do dia (tabela com busca e ordenação).
3. Clicar num evento **sem médico alocado** (ou numa linha da lista) abre
   direto o modal **Cadastro de Agenda**, com formulário completo (unidade,
   sala, médico inicial/substituto, horários, procedimentos dinâmicos,
   valor previsto/real e tipo de cálculo de pagamento).

Os botões "Exportar relatório" e "Configurações" são apenas de fachada,
sem funcionalidade real.
