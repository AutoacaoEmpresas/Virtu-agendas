# Virtù — Protótipo

Protótipo funcional em Django do sistema Virtù: ferramenta de agendamento de
procedimentos oftalmológicos realizados por médicos em diferentes unidades de
saúde. Objetivo: validar o modelo de dados e o fluxo das 3 telas principais
(tela inicial com calendário, lista de agendamentos do dia e cadastro de
agenda), além do controle de acesso por cargo. Não possui testes
automatizados ou preocupação com produção — é apenas para rodar localmente
com dados fictícios.

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
seed_data` novamente (ele apaga e recria tudo, exceto os usuários — que são
recriados só se não existirem).

## Autenticação e cargos

Existem 3 cargos, cada um com um conjunto de permissões:

- **Administrador**: acesso total (agendas, médicos, unidades, salas,
  procedimentos, usuários) e ao `/admin/` do Django. Login exige uma
  **verificação em duas etapas por e-mail**: depois da senha, um código de 6
  dígitos é enviado para o e-mail cadastrado (em desenvolvimento, o backend de
  e-mail é `console` — o código aparece direto no terminal onde o
  `runserver` está rodando).
- **Agendamento**: pode criar, editar e excluir **agendas** e **médicos**,
  mas só dentro das **unidades liberadas** para aquele usuário (o
  Administrador escolhe quais, em `/admin/`, no cadastro do usuário — pode
  ser uma ou várias). Sem OTP no login.
- **Concierge**: só **vê** agendas (também restrito por unidade) e só pode
  editar a **quantidade de pacientes reais** de cada procedimento de uma
  agenda já existente. Sem OTP no login.

`python manage.py seed_data` já cria 4 usuários de demonstração (senha
`Virtu@123` para todos):

| Usuário | Cargo | Unidades visíveis |
|---|---|---|
| `admin` | Administrador | todas |
| `agendamento1` | Agendamento | 1ª unidade |
| `agendamento2` | Agendamento | 2ª e 3ª unidades |
| `concierge1` | Concierge | 1ª unidade |

Para criar um novo Administrador direto pela linha de comando (sem passar
pelo `/admin/`): `python manage.py createsuperuser` (vai pedir usuário,
e-mail e senha).

## Estrutura

- `virtu_config/` — configuração do projeto Django (settings, urls raiz).
- `contas/` — app de autenticação: model de usuário customizado (`Usuario`,
  com cargo e unidades permitidas), login com OTP por e-mail para
  Administrador, logout.
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
