# Guia do Projeto — Virtù

Este documento explica **o que cada arquivo faz**, **os conceitos de Django por trás dele** e **como mexer no código para adicionar ou melhorar funcionalidades**. A ideia é que você consiga ler isso e sair sabendo, por exemplo, "quero adicionar um campo X" ou "quero mudar essa regra de negócio" e onde exatamente ir.

> Se você nunca usou Django: é um *framework* Python para construir sites que seguem o padrão **MVT** (Model-View-Template) — uma variação do MVC. Resumindo o ciclo de uma requisição:
>
> 1. O navegador pede uma URL (`/dia/2026-09-04/agendamentos/`).
> 2. O Django olha o **urls.py** e descobre qual **view** (função Python) trata essa URL.
> 3. A view busca/salva dados usando os **models** (que representam tabelas do banco).
> 4. A view manda os dados para um **template** (HTML com uma mini-linguagem de template).
> 5. O template vira HTML final, que volta pro navegador.
>
> Guarde esse ciclo — ele se repete em todo lugar do projeto.

---

## 1. Estrutura geral de pastas

```
Virtu-agendas/
├── manage.py                  # ponto de entrada de comandos Django
├── requirements.txt           # dependências Python do projeto
├── db.sqlite3                 # banco de dados (gerado, não editar à mão)
├── virtu_config/               # configuração global do projeto (o "cérebro")
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
└── agendas/                    # o "app" (módulo) com a funcionalidade real
    ├── models.py               # estrutura do banco de dados
    ├── views.py                # lógica das telas
    ├── urls.py                 # rotas do app
    ├── admin.py                # painel administrativo
    ├── apps.py                 # metadados do app
    ├── migrations/              # histórico de mudanças no banco
    ├── management/commands/     # comandos customizados (seed_data)
    ├── templates/agendas/        # HTML
    └── static/agendas/           # CSS e JS
```

Um projeto Django é dividido em **project** (`virtu_config`, a configuração geral — pode ter várias apps) e **apps** (`agendas`, um módulo autocontido de funcionalidade). Um projeto grande normalmente tem várias apps (`usuarios`, `financeiro`, `agendas`...); aqui só existe uma.

---

## 2. `manage.py`

Utilitário de linha de comando. É por ele que você roda tudo:

```bash
python manage.py runserver        # sobe o servidor local
python manage.py migrate          # aplica mudanças de models no banco
python manage.py makemigrations   # gera arquivos de migração a partir de mudanças em models.py
python manage.py createsuperuser  # cria um usuário para o /admin/
python manage.py seed_data        # popula com dados fictícios (comando customizado)
python manage.py shell            # abre um Python interativo com o Django carregado
```

Não precisa editar esse arquivo nunca.

---

## 3. `virtu_config/` — configuração do projeto

### `settings.py`
O arquivo mais importante para configuração. Pontos-chave hoje:

- `INSTALLED_APPS`: lista de apps ativos (`agendas` está aqui — se você criar uma app nova, precisa registrá-la aqui).
- `MIDDLEWARE`: uma "esteira" de funções que processam toda requisição/resposta (sessão, CSRF, segurança, etc). A ordem importa.
- `DATABASES`: hoje aponta pro SQLite (`db.sqlite3`), um banco em arquivo único — ótimo para prototipagem, mas não aguenta muita concorrência. Trocar para Postgres é só mudar esse dicionário (e instalar `psycopg2`).
- `TEMPLATES`: diz ao Django onde procurar arquivos `.html` (por padrão, dentro de `<app>/templates/`).
- `STATIC_URL` / `STATIC_ROOT` / `STORAGES`: onde ficam CSS/JS e como eles são servidos (ver seção sobre deploy/whitenoise abaixo).
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`: agora lidos de variáveis de ambiente (mudança feita para permitir deploy em produção no Render) — em desenvolvimento local, se você não setar nada, cai nos valores padrão (`DEBUG=True`, chave insegura, hosts liberados).

**Quando mexer aqui:** ao adicionar uma nova app, trocar de banco de dados, mudar idioma/fuso horário, ou configurar algo novo como envio de e-mail.

### `urls.py` (raiz)
```python
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('agendas.urls')),
]
```
É o "índice" de rotas do projeto inteiro. Ele delega tudo que não é `/admin/` para o arquivo `agendas/urls.py` via `include()`. Se você criar uma segunda app (ex: `financeiro`), adicionaria aqui `path('financeiro/', include('financeiro.urls'))`.

### `wsgi.py` / `asgi.py`
Pontes técnicas entre o Django e o servidor web (Gunicorn, uWSGI, etc). Você não edita isso no dia a dia — só é relevante saber que é o `wsgi.py` que o Gunicorn usa em produção (`gunicorn virtu_config.wsgi`).

---

## 4. `agendas/models.py` — o coração dos dados

Cada classe aqui vira uma **tabela** no banco. Cada atributo vira uma **coluna**. Este é provavelmente o arquivo mais importante para entender antes de mexer em qualquer coisa.

### Conceitos usados

- **`CharField`, `DecimalField`, `DateField`, `TimeField`, `BooleanField`, `EmailField`**: tipos de coluna. `CharField` sempre precisa de `max_length`.
- **`ForeignKey`** (relação N:1): ex. `Sala.unidade` — cada sala pertence a **uma** unidade, uma unidade tem **várias** salas. `related_name="salas"` é o nome que você usa para ir no sentido contrário: `unidade.salas.all()`.
- **`on_delete`**: o que fazer quando o registro apontado é apagado.
  - `CASCADE`: apaga em cascata (ex: apagar uma `Unidade` apaga suas `Sala`s).
  - `SET_NULL`: zera o campo em vez de apagar (usado em `Medico` — se apagar um médico, a agenda não é destruída, só fica "sem médico"). Exige `null=True`.
- **`OneToOneField`**: `Agenda.horario` — cada agenda tem exatamente um horário e vice-versa (é como um `ForeignKey` com restrição de unicidade).
- **`ManyToManyField` com `through=`**: relação N:N onde você precisa guardar informação extra sobre a relação.
  - `Medico.unidades` usa a tabela intermediária `UnidadeMedico` (só liga médico↔unidade).
  - `Agenda.procedimentos` usa `ProcedimentoAgenda`, que guarda **campos extras** por procedimento daquela agenda (`esperanca_pacientes`, `real_pacientes`) — é assim que uma agenda pode ter "Cirurgia de Catarata: 3 pacientes esperados" e "Consulta: 1 paciente esperado" ao mesmo tempo.
- **`class Meta`**: configurações que não são colunas — nome de exibição (`verbose_name`), ordenação padrão (`ordering`), restrição de unicidade (`unique_together`).
- **`__str__`**: como o objeto aparece quando impresso ou no admin (ex: numa lista suspensa). Sempre vale a pena definir.
- **`@property`**: um método que se comporta como atributo. Ex:
  - `Horario.turno`: calcula "Manhã/Tarde/Noite" a partir do horário de início — não fica salvo no banco, é calculado toda vez que você acessa `horario.turno`.
  - `Agenda.sala` / `Agenda.unidade`: atalhos pra não escrever `agenda.horario.salas.first()` toda hora.
  - `Agenda.valor_previsto`: soma `valor_base * esperanca_pacientes` de cada procedimento da agenda — é a regra de negócio "quanto essa agenda deve faturar".

### Mapa das entidades

```
Unidade ──< Sala ──< SalaHorario >── Horario ── Agenda >── ProcedimentoAgenda >── Procedimento
   │                                              │
   └──< Procedimento                              ├── medico_inicial ─┐
                                                    ├── medico_atendido ┤→ Medico ──< UnidadeMedico >── Unidade
                                                                        │        └── conta_bancaria → ContaBancaria
```

- `Unidade`: uma clínica/hospital.
- `Sala`: pertence a uma unidade.
- `Horario`: uma data + faixa de horário; pode estar ligada a uma ou mais salas via `SalaHorario` (na prática, hoje o app sempre usa 1 sala por horário).
- `Agenda`: o "evento" central — liga um `Horario` a médico(s) e procedimento(s), guarda valores e confirmação.
- `Medico`: pode atuar em várias unidades (`UnidadeMedico`) e tem uma conta bancária.
- `Procedimento`: pertence a uma unidade e tem um valor base.

**Como adicionar um campo novo** (ex: `Medico.crm`):
1. Adicione a linha em `models.py`: `crm = models.CharField(max_length=20, blank=True)`.
2. Rode `python manage.py makemigrations` — isso gera um arquivo novo em `agendas/migrations/` descrevendo a mudança.
3. Rode `python manage.py migrate` — aplica a mudança no `db.sqlite3` de verdade.
4. Se quiser editar esse campo no admin ou nos formulários, atualize `admin.py` / os templates / `views.py` (ver seções abaixo).

**Como adicionar uma entidade nova** (ex: `Paciente`): crie uma nova classe em `models.py` seguindo o mesmo padrão, depois `makemigrations` + `migrate`.

---

## 5. `agendas/migrations/`

Cada arquivo aqui é um "commit" de mudanças no esquema do banco, gerado automaticamente pelo `makemigrations`. `0001_initial.py` é a criação de todas as tabelas do zero.

**Regra de ouro:** nunca edite um arquivo de migração já aplicado nem apague `db.sqlite3` sem necessidade — deixe o Django gerar e aplicar as migrações. Se dois desenvolvedores criarem migrações conflitantes, o Django avisa e você resolve com `makemigrations --merge`.

---

## 6. `agendas/views.py` — a lógica das telas

Views em Django são só **funções Python que recebem um `request` e devolvem uma resposta** (geralmente HTML renderizado, via `render()`).

### `home(request)`
Tela principal (calendário semanal). Passo a passo:
1. Descobre qual semana mostrar (`?semana=2026-09-01` na URL, ou hoje por padrão) — função auxiliar `_monday()` acha a segunda-feira daquela semana.
2. Monta um **queryset** (`Agenda.objects.select_related(...).prefetch_related(...).filter(...)`) — isso é o ORM do Django traduzindo Python em SQL. `select_related`/`prefetch_related` existem só para performance (evitar 1 query por linha — o famoso "N+1 queries").
3. Aplica filtros de busca (`Q(...)  | Q(...)` = "OU" nas condições) e de unidade, se vieram na URL.
4. Monta a lista `dias_semana`, agrupando os eventos por dia, com cor por unidade (`_cor_unidade`).
5. Monta o mini-calendário do mês (usando `calendar.Calendar` da biblioteca padrão do Python) e marca quais dias têm agenda.
6. Monta a lista lateral de "agendas abertas" (sem médico).
7. Manda tudo isso num dicionário `context` para o template `agendas/home.html`.

**Onde mexer:** se quiser mudar a regra de cores, `_cor_unidade`. Se quiser um novo filtro (ex: por médico), adicione a leitura do parâmetro (`request.GET.get(...)`) e um `.filter()` no queryset, depois exponha o campo no template.

### `lista_agendamentos(request, data)`
View chamada via **fetch/AJAX** (veja `main.js`) para carregar o conteúdo do modal "Lista de Agendamentos" sem recarregar a página. Recebe a data pela URL (`/dia/2026-09-04/agendamentos/`), filtra e ordena, e renderiza só o **fragmento** `_lista_agendamentos.html` (não a página inteira) — é por isso que ele não usa `{% extends %}`.

### `cadastro_agenda(request, agenda_id=None)`
Mesma view atende **criar** e **editar** uma agenda:
- Se vier `agenda_id` na URL, carrega a agenda existente (pré-preenche o formulário).
- Se o método for `GET`, apenas renderiza o formulário (fragmento `_cadastro_agenda.html`).
- Se o método for `POST` (formulário enviado), delega para `_salvar_agenda`.

### `_salvar_agenda(request, agenda)`
A função com a regra de negócio mais complexa do projeto. O `@transaction.atomic` no topo garante que, se algo der erro no meio, **nada** é salvo (tudo ou nada — evita ficar com "meia agenda" salva no banco).

Lógica principal:
- Decide quem é o "médico atendido" (o que efetivamente vai atender): se tem substituto, é o substituto; senão, é o médico inicial só se ele estiver marcado como "confirmado".
- Trata **recorrência**: se a frequência for "semanal" e houver data final, gera uma lista de datas (uma por semana) e cria uma `Agenda` + `Horario` para cada uma, num loop.
- Para cada data, apaga os procedimentos antigos daquela agenda (`.delete()`) e recria a partir do que veio no formulário (`request.POST.getlist(...)` — pega múltiplos campos com o mesmo `name="procedimento[]"`, um padrão de "linhas dinâmicas" repetidas no formulário).
- No final, redireciona pro `home` (`redirect("agendas:home")`).

**Onde mexer:** se quiser mudar a regra de "quem é o médico atendido", trocar recorrência de semanal para diária/mensal, ou validar campos (hoje não há validação de formulário de verdade — ver seção 10, "Próximos passos").

---

## 7. `agendas/urls.py` — rotas do app

```python
app_name = "agendas"
urlpatterns = [
    path("", views.home, name="home"),
    path("dia/<str:data>/agendamentos/", views.lista_agendamentos, name="lista_agendamentos"),
    path("agenda/nova/", views.cadastro_agenda, name="cadastro_agenda_nova"),
    path("agenda/<int:agenda_id>/editar/", views.cadastro_agenda, name="cadastro_agenda_editar"),
]
```
- `<str:data>` e `<int:agenda_id>` são **conversores de tipo**: o Django extrai esse pedaço da URL e passa como argumento pra view já convertido.
- `app_name = "agendas"` + `name="home"` permitem referenciar a URL nos templates/código sem hardcodar o caminho: `{% url 'agendas:home' %}` ou `redirect("agendas:home")`. Isso é importante — se você mudar o caminho da URL aqui, não precisa achar e trocar em todo template.

**Como adicionar uma rota nova:** adicione uma linha `path(...)` aqui apontando pra uma função em `views.py`.

---

## 8. `agendas/admin.py`

Registra os models no painel `/admin/` (interface administrativa que o Django gera sozinho). Hoje é um registro básico (`admin.site.register(Modelo)`), então o admin mostra os campos padrão.

**Como melhorar:** trocar `admin.site.register(Medico)` por uma classe customizada, ex:
```python
@admin.register(Medico)
class MedicoAdmin(admin.ModelAdmin):
    list_display = ("nome", "especialidade", "email")
    search_fields = ("nome", "especialidade")
    list_filter = ("especialidade",)
```
Isso deixa a lista do admin pesquisável e filtrável — bem mais fácil de inspecionar dados sem escrever SQL.

---

## 9. `agendas/apps.py`

Só metadados da app (nome, tipo de chave primária padrão). Raramente precisa editar, exceto para "sinais" (signals) do Django, que ficam registrados no método `ready()` — um tópico mais avançado.

---

## 10. `agendas/management/commands/seed_data.py`

Comando customizado (`python manage.py seed_data`) que popula o banco com dados fictícios e determinísticos (`random.seed(42)` garante que rodar duas vezes gera os mesmos dados). Estrutura de um comando Django:
- Herda de `BaseCommand`.
- `add_arguments`: define flags de linha de comando (aqui, `--sem-limpar`, pra não apagar dados antes de popular).
- `handle()`: o código que roda de fato.

Ele cria, em ordem (respeitando as dependências entre models): unidades → salas → contas bancárias → médicos → procedimentos → horários/agendas para 2 semanas.

**Como usar para testar:** se quiser um cenário específico (ex: "quero muitos médicos sem confirmação"), edite as listas no topo do arquivo (`MEDICOS`, `PROCEDIMENTOS`) ou as probabilidades (`random.random() > 0.2`) e rode `seed_data` de novo.

---

## 11. Templates (`agendas/templates/agendas/`)

Motor de template do Django: HTML normal + tags `{% %}` (lógica) e `{{ }}` (variáveis/valores).

### `base.html`
O "molde" de toda página: `<head>`, navbar, e dois `<div class="modal">` vazios que servem de "moldura" — o conteúdo deles é injetado depois via JavaScript (`fetch` + `innerHTML`). Carrega Bootstrap via CDN, `style.css` e `main.js` via `{% static %}` (tag que resolve o caminho certo pros arquivos estáticos).

### `home.html`
Estende `base.html` com `{% extends "agendas/base.html" %}` e preenche o `{% block content %}`. Contém:
- O mini-calendário (`{% for semana in semanas_mes %}` dentro de `{% for dia in semana %}` — um loop dentro do outro, mês → semanas → dias).
- A lista de agendas abertas.
- A grade semanal com os "cards" de evento (`evento-card`), cada um com `data-agenda-id` e `data-tem-medico` — atributos lidos pelo JavaScript pra decidir o que fazer ao clicar.

### `partials/_cadastro_agenda.html` e `partials/_lista_agendamentos.html`
Começam com `_` por convenção (indica "fragmento parcial", não uma página completa) e **não** estendem `base.html` — são renderizados isoladamente e injetados dentro dos modais via JS. Esse padrão ("HTML fragments over AJAX", às vezes chamado de HTML-over-the-wire) evita ter que escrever uma API JSON + JavaScript pra montar a tela: o servidor já manda o HTML pronto.

**Conceitos de template úteis pra saber:**
- `{% if %}/{% for %}/{% empty %}`: `{% empty %}` roda quando o `for` não tem itens (ótimo pra "nenhum resultado encontrado").
- Filtros (`|`): `{{ dia|date:"d/m" }}` formata data, `{{ valor|default:"0,00" }}` dá um valor padrão, `{{ x|yesno:"1,0" }}` transforma booleano em texto.
- `{% csrf_token %}`: obrigatório em todo `<form method="post">` — é a proteção contra ataques CSRF (Cross-Site Request Forgery); sem ele, o Django rejeita o POST.

**Como adicionar um campo no formulário de cadastro:** edite `_cadastro_agenda.html` adicionando o `<input>`/`<select>` com um `name="..."`, depois vá em `_salvar_agenda` (`views.py`) e leia esse campo com `post.get("nome_do_campo")`, e por fim use esse valor ao criar/atualizar o objeto.

---

## 12. Estáticos (`agendas/static/agendas/`)

### `js/main.js`
Não usa nenhum framework (React/Vue) — é **JavaScript puro** com um padrão chamado **delegação de eventos**: em vez de colocar um `addEventListener` em cada botão (que nem existem ainda quando a página carrega, pois vêm de HTML injetado depois), ele registra **um único listener no `document`** para `click`, `submit` e `change`, e usa `e.target.closest(".classe")` pra descobrir o que foi clicado. Isso é essencial aqui porque o conteúdo dos modais é gerado dinamicamente (não existe no HTML inicial), então listeners "diretos" não funcionariam.

Funções principais:
- `loadListaAgendamentos(dia, params)` / `loadCadastroAgenda(agendaId, extraParams)`: fazem `fetch()` pra buscar o HTML do fragmento no servidor e jogam em `innerHTML`, depois abrem o modal do Bootstrap (`bootstrap.Modal`).
- `filtrarPorUnidade(unidadeId)`: esconde (`hidden`) as opções de sala/procedimento que não pertencem à unidade selecionada — filtro client-side, sem ida ao servidor.
- Handlers de "+ Adicionar"/"remover linha" de procedimento: clonam (`cloneNode`) a primeira linha da tabela pra criar novas linhas dinâmicas.

**Como adicionar um comportamento novo:** siga o padrão — adicione um `if (e.target.closest(".sua-classe"))` dentro do listener de `click` já existente, em vez de criar um novo `addEventListener`.

### `css/style.css`
CSS customizado por cima do Bootstrap (que vem do CDN). Cada bloco corresponde a um componente visual específico: mini-calendário, lista de agendas abertas (com scroll), grade semanal (`week-grid`, com scroll horizontal), cards de evento (`evento-card`, com o padrão listrado `evento-vazio` pra vagas em aberto).

---

## 13. Arquivos de infraestrutura (adicionados para deploy)

- **`requirements.txt`**: lista de pacotes Python e versões exatas. `pip install -r requirements.txt` instala tudo. Inclui agora `gunicorn` (servidor de produção) e `whitenoise` (serve arquivos estáticos direto pelo Django, sem precisar de Nginx/CDN separado).
- **`build.sh`**: script rodado pelo Render antes de cada deploy — instala dependências, roda `collectstatic` (empacota CSS/JS num único lugar) e `migrate`/`seed_data`.
- **`.gitignore`**: arquivos que não devem ir pro Git (`venv/`, `db.sqlite3`, cache do Python, etc) — evita subir lixo ou dados locais pro repositório.

---

## 14. Conceitos-chave para você reter

| Conceito | O quê | Onde ver no projeto |
|---|---|---|
| ORM | Escrever `Model.objects.filter(...)` em vez de SQL na mão | `views.py` inteiro |
| Migration | Histórico versionado de mudanças no banco | `agendas/migrations/` |
| `select_related` / `prefetch_related` | Evitar N+1 queries ao buscar dados relacionados | `home()`, `lista_agendamentos()` |
| `QuerySet` é "preguiçoso" (lazy) | Um `.filter()` não bate no banco até você iterar/usar o resultado | permite empilhar `.filter().filter()` sem custo extra |
| Namespacing de URLs | `app_name` + `{% url 'agendas:home' %}` | `agendas/urls.py` |
| CSRF token | Proteção obrigatória em formulários POST | todo `<form method="post">` |
| Fragmentos HTML via fetch | Alternativa simples a uma API JSON + frontend JS complexo | `lista_agendamentos`, `cadastro_agenda`, `main.js` |
| `@transaction.atomic` | Tudo-ou-nada ao salvar múltiplas tabelas juntas | `_salvar_agenda` |

---

## 15. Próximos passos sugeridos (para você aprender fazendo)

Pequenos exercícios, do mais simples ao mais avançado:

1. **Fácil** — Adicione um campo `crm` em `Medico` (models → migration → admin → template do formulário).
2. **Fácil** — Customize `admin.py` com `list_display`/`search_fields` pra pelo menos `Medico` e `Agenda`.
3. **Médio** — Adicione uma página `/medicos/` que lista todos os médicos (nova view + nova rota + novo template estendendo `base.html`).
4. **Médio** — Adicione validação real no formulário de cadastro de agenda (hoje `_salvar_agenda` confia cegamente no que vem do POST). Dica: pesquise `django.forms.ModelForm` — é o jeito "certo" do Django de validar dados de formulário, em vez de ler `request.POST` na mão.
5. **Avançado** — Adicione autenticação (`django.contrib.auth`) pra exigir login antes de acessar `/` e `/admin/` (hoje qualquer pessoa com a URL acessa tudo — README já avisa que não há autenticação).
6. **Avançado** — Troque SQLite por Postgres nas configurações (`DATABASES` em `settings.py`) pra rodar num ambiente mais próximo de produção real.

Sempre que mexer em `models.py`, lembre do ciclo: **editar → `makemigrations` → `migrate`**. Esquecer esse passo é o erro mais comum ao aprender Django (a mudança "não aparece" porque o banco ainda não sabe dela).
