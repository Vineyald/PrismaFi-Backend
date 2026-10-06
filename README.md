# PrismaFi Backend

API do PrismaFi, construída como um **monólito modular** em FastAPI.

O PrismaFi é um SaaS financeiro que dá ao usuário uma visão centralizada da sua vida financeira. Ele vai reunir instituições conectadas via Open Finance, contas bancárias, saldos, transações e contas a pagar, além da iniciação de pagamentos. O PrismaFi **orquestra a experiência**; a operação financeira em si é executada por infraestrutura regulada (provedor de Open Finance / iniciação de pagamento). O PrismaFi **nunca recebe nem repassa o dinheiro do usuário**.

Hoje este repositório contém apenas a fundação técnica: configuração, PostgreSQL, Redis, broker de jobs em background e um endpoint de health check. Ainda não há funcionalidades de produto (veja o [Roadmap até o MVP](#roadmap-até-o-mvp)).

O frontend fica em um repositório separado (`PrismaFi-Frontend`). Os dois se integram **somente** via HTTP e pelo schema OpenAPI publicado aqui.

## Responsabilidades deste repositório

| Pertence ao backend | Não pertence ao backend |
|---|---|
| Regras de negócio e modelo de domínio | Layout, UX e acessibilidade |
| Validação de dados (o backend é a fronteira de confiança) | Validação de formulário só para usabilidade |
| Persistência, migrations e integridade (constraints, transações) | Estado de tela |
| Autenticação, sessões e autorização | Guards de rota (que só melhoram a UX; quem protege é o backend) |
| Cálculos monetários (`Decimal` / `NUMERIC`) | Formatação de valores para exibição |
| Integrações: provedor de Open Finance, iniciação de pagamento, webhooks | Renderização dos fluxos expostos pela API |
| Workers, sincronização e reconciliação | — |
| Contrato OpenAPI (fonte da verdade) | Tipos TypeScript gerados a partir desse contrato |

## Stack tecnológica

| Tecnologia | Por que está aqui |
|---|---|
| **Python 3.12+** (desenvolvido em 3.14) | Ecossistema forte para finanças, dados e integrações. `requires-python >= 3.12`; a imagem Docker usa 3.14. |
| **FastAPI** | Framework HTTP assíncrono. Gera o schema OpenAPI a partir do código tipado, e esse schema é o contrato com o frontend. |
| **Pydantic v2** / **pydantic-settings** | Validação e serialização de requests/responses; configuração tipada a partir de variáveis de ambiente. |
| **SQLAlchemy 2** (async) + **asyncpg** | ORM e camada de queries com driver PostgreSQL assíncrono. |
| **PostgreSQL** | Banco principal: integridade transacional, `NUMERIC` para dinheiro e constraints para garantir idempotência. |
| **Alembic** | Migrations versionadas do schema. |
| **Redis** | Cache e broker de mensagens. |
| **Dramatiq** | Jobs em background (sincronização com o provedor, webhooks, notificações), com Redis como broker. Escolhido em vez do Celery por ter um modelo mais simples e uma superfície menor. |
| **httpx** | Usado hoje pelo `TestClient` do FastAPI. Será o cliente HTTP de saída das integrações com provedores; nesse momento passa para as dependências de runtime. |
| **Uvicorn** | Servidor ASGI. |
| **Pytest** | Testes. |
| **Ruff** | Linter e formatter. Regras: pycodestyle, pyflakes, isort, pyupgrade, bugbear, armadilhas de async e checagens de segurança do bandit. |
| **mypy** (strict) | Tipagem estática, com o plugin do Pydantic. |
| **Docker / Docker Compose** | Stack local com um comando: API, worker, PostgreSQL e Redis. |

## Arquitetura

Monólito modular com fronteiras claras e sem cerimônia: uma camada só é criada quando resolve um problema real.

```text
PrismaFi-Backend/
├── app/
│   ├── core/              # Infraestrutura compartilhada por todos os módulos
│   │   ├── config.py      # Settings (variáveis de ambiente / .env), validadas na inicialização
│   │   ├── database.py    # Engine async + Base declarativa com convenção de nomes de constraints
│   │   ├── redis.py       # Cliente Redis async compartilhado
│   │   └── broker.py      # Broker Redis do Dramatiq
│   ├── health.py          # GET /api/health (readiness: banco + Redis)
│   └── main.py            # Montagem da aplicação: routers, CORS, handler de erros, lifespan
├── migrations/
│   ├── env.py             # Ambiente do Alembic: usa as settings da aplicação e Base.metadata
│   ├── script.py.mako     # Template de revisão
│   └── versions/          # Revisões (nenhuma ainda)
├── tests/
│   ├── conftest.py        # Força settings de teste, independentes do seu .env
│   └── test_health.py
├── .env.example
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

**Responsabilidades**

- `app/core/` contém só infraestrutura e nunca importa módulos de negócio.
- `app/main.py` conecta tudo. É o único lugar que conhece todos os routers.
- Os domínios de negócio (`users`, `auth`, `accounts`, `transactions`, `obligations`, `payments`, …) vão ficar em `app/modules/<nome>/`. Cada módulo tem seu `router.py`, `schemas.py` (Pydantic), `models.py` (SQLAlchemy) e `service.py` (regras de negócio), e ganha um `tasks.py` com actors do Dramatiq só quando precisar. Routes ficam finas; a lógica de negócio fica no service. Uma camada de repository só entra se eliminar duplicação ou complexidade real.
- Integrações externas (ex.: o provedor de Open Finance) ficam isoladas em `app/integrations/<provedor>/`: funções que chamam o provedor e já devolvem tipos do PrismaFi. Payloads específicos do provedor nunca circulam pelo domínio. Uma interface abstrata (`Protocol`) só entra quando houver um segundo provedor.
- Dependências entre módulos têm direção única. Ex.: `payments` chama o service de `obligations` para marcar uma obrigação como paga; `obligations` nunca importa `payments`.
- **Nenhuma dessas pastas existe ainda, de propósito.** Não criamos arquitetura vazia para código hipotético: `app/modules/` nasce com o primeiro domínio real.

**Layout da API**

Tudo é servido sob `/api`, para que o frontend acesse a API por um único caminho de mesma origem: hoje pelo proxy de desenvolvimento do Angular, em produção por um reverse proxy.

| Caminho | Finalidade |
|---|---|
| `/api/health` | Health check sem versão, para probes de infraestrutura |
| `/api/v1/...` | Endpoints de negócio (versionados); nenhum ainda |
| `/api/docs`, `/api/redoc`, `/api/openapi.json` | Documentação da API (somente em desenvolvimento) |

## Configuração do ambiente

Pré-requisitos: Python 3.12+, Docker Desktop (no Windows exige WSL 2) e Git.

```bash
# 1. Clonar
git clone <repo-url> PrismaFi-Backend
cd PrismaFi-Backend

# 2. Variáveis de ambiente
cp .env.example .env            # ajuste os valores se precisar

# 3. Dependências Python (para testes, lint, IDE e comandos rodados no host)
python -m venv .venv            # Windows: py -3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 4. Subir a stack completa: PostgreSQL, Redis, API (hot reload) e worker.
#    O serviço api roda `alembic upgrade head` antes de iniciar.
docker compose up --build

# 5. Conferir
curl http://localhost:8000/api/health
```

A API fica em http://localhost:8000 e a documentação em http://localhost:8000/api/docs.

**Rodando a API no host em vez do Docker** (útil para usar um debugger):

```bash
docker compose up -d db redis
alembic upgrade head
uvicorn app.main:app --reload
```

**Testes e qualidade**

```bash
pytest
ruff check .
ruff format --check .
mypy app migrations tests
```

## Variáveis de ambiente

Todas estão definidas no `.env.example`. As settings são validadas na inicialização: um valor obrigatório ausente ou inválido impede a aplicação de subir.

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `ENVIRONMENT` | não | `production` | `development` ou `production`. Em produção, `/api/docs`, `/api/redoc` e `/api/openapi.json` ficam desativados. O padrão é seguro: um deploy que esquecer a variável sobe com comportamento de produção. |
| `LOG_LEVEL` | não | `INFO` | `DEBUG`, `INFO`, `WARNING` ou `ERROR`. |
| `POSTGRES_USER` | compose | — | Usuário criado pelo container do Postgres; também usado para montar o `DATABASE_URL` dos containers. |
| `POSTGRES_PASSWORD` | compose | — | Senha desse usuário. Use só caracteres seguros para URL (letras, dígitos, `- _ .`), porque ela entra na URL sem encoding. |
| `POSTGRES_DB` | compose | — | Nome do banco. |
| `DATABASE_URL` | **sim** | — | `postgresql+asyncpg://user:pass@host:5432/db`. No `.env` aponta para `localhost`, para comandos rodados no host, e precisa bater com os valores `POSTGRES_*`. O Compose troca o host para `db` dentro dos containers. |
| `REDIS_URL` | **sim** | — | `redis://host:6379/0`. O Compose troca o host para `redis`. |
| `CORS_ORIGINS` | não | `[]` | Lista JSON de origens de navegador permitidas, ex.: `["https://app.example.com"]`. Vazia desativa o CORS, o que é o correto enquanto o frontend estiver na mesma origem. |

Valores vazios (`VAR=`) caem no padrão. Segredos reais nunca entram no repositório: `.env`, `.env.*`, `*.pem`, `*.key` e `*.p12` estão no `.gitignore` e no `.dockerignore`.

## Banco de dados

- **PostgreSQL 18** roda no Docker Compose, com os dados no volume `postgres-data`. A porta é publicada só em `127.0.0.1:5432`.
- **SQLAlchemy 2 async**: `app/core/database.py` expõe o `engine` e a `Base` declarativa.
  - `Base.metadata` tem uma **convenção de nomes** para índices e constraints, para o Alembic conseguir alterá-los e removê-los de forma confiável.
  - O engine usa `hide_parameters=True`, que omite os parâmetros bindados (valores monetários, identificadores, tokens) das mensagens do SQLAlchemy. Atenção: mensagens geradas pelo próprio PostgreSQL (como o `DETAIL` de uma violação de unique constraint: `Key (email)=(...) already exists`) ainda podem conter valores. Por isso, services capturam `IntegrityError` e o convertem em erro de domínio, e o texto bruto de exceções do banco nunca é logado.
  - A session factory e a dependency `get_session` entram aqui junto com o primeiro model. Nada precisa delas ainda.
- O **Alembic** lê a URL das settings da aplicação. O `alembic.ini` não tem credenciais.

**Fluxo de migrations**

```bash
# 1. Crie/altere models em app/modules/<nome>/models.py
# 2. Importe o módulo de models em migrations/env.py (para o autogenerate enxergá-lo)
alembic revision --autogenerate -m "create accounts table"
# 3. Revise o arquivo gerado em migrations/versions/. O autogenerate é um rascunho, não a verdade.
alembic upgrade head
alembic downgrade -1          # toda migration precisa ser reversível
alembic upgrade head --sql    # imprime o SQL sem banco (revisão / produção)
```

Novas revisões passam automaticamente por `ruff check --fix` e `ruff format` (`post_write_hooks` no `alembic.ini`).

## Jobs em background

- `app/core/broker.py` cria o `RedisBroker` do Dramatiq a partir do `REDIS_URL` e o registra globalmente.
- O serviço `worker` do Compose roda `dramatiq app.core.broker --processes 1 --threads 2`.
- **Ainda não existe nenhum actor.** O worker sobe e conecta no Redis, pronto para o primeiro job real. Nenhum job fictício foi criado.

Para adicionar um job:

```python
# app/modules/<nome>/tasks.py
import dramatiq
from app.core.broker import broker


@dramatiq.actor(broker=broker, max_retries=5)
def sync_connection(connection_id: str) -> None: ...
```

Depois, adicione o módulo ao comando do worker: `dramatiq app.core.broker app.modules.<nome>.tasks`. Jobs precisam ser **idempotentes**, porque o Dramatiq refaz a execução em caso de falha.

O Dramatiq não tem agendador periódico nativo. Quando surgir o primeiro job agendado (ex.: lembrete de vencimento), a escolha do agendador entra como decisão explícita.

## API

| URL | O que é |
|---|---|
| http://localhost:8000/api/docs | Swagger UI (somente em desenvolvimento) |
| http://localhost:8000/api/redoc | ReDoc (somente em desenvolvimento) |
| http://localhost:8000/api/openapi.json | Schema OpenAPI 3.1 (somente em desenvolvimento). O frontend gera seus tipos TypeScript a partir dele. |
| `GET /api/health` | Readiness |

`GET /api/health` verifica o PostgreSQL (`SELECT 1`) e o Redis (`PING`) em paralelo, com timeout de 2s para cada um:

```json
// 200 OK
{ "status": "healthy", "service": "prismafi-backend", "checks": { "database": "ok", "redis": "ok" } }
// 503 Service Unavailable
{ "status": "unhealthy", "service": "prismafi-backend", "checks": { "database": "unavailable", "redis": "ok" } }
```

Falhas são logadas só pelo tipo da exceção, porque mensagens de driver podem conter detalhes da conexão. Erros não tratados retornam `500 {"detail": "Internal server error"}` sem expor detalhes internos; o traceback vai para o log do servidor.

## Qualidade

| Ferramenta | Comando | Configuração |
|---|---|---|
| Ruff (lint) | `ruff check .` | `[tool.ruff]` no `pyproject.toml` |
| Ruff (format) | `ruff format .` | idem |
| mypy | `mypy app migrations tests` | `strict = true` + plugin do Pydantic |
| Pytest | `pytest` | `tests/` |

Os testes atuais cobrem:

- o health check nos estados saudável e com dependência fora do ar (com os pings das dependências simulados);
- a resposta 500 genérica, que não pode vazar detalhes internos;
- a documentação e o schema escondidos quando `ENVIRONMENT=production`.

## Docker

`docker compose up --build` sobe:

| Serviço | Imagem | Observações |
|---|---|---|
| `api` | build do `Dockerfile` | Roda `alembic upgrade head` e depois `uvicorn --reload`. `./app` e `./migrations` são montados via bind mount, então edições recarregam na hora (com polling, porque bind mounts no Windows não propagam eventos de arquivo). Porta `127.0.0.1:8000`. |
| `worker` | mesma imagem | O worker do Dramatiq. |
| `db` | `postgres:18-alpine` | Health check via TCP. Porta `127.0.0.1:5432`. |
| `redis` | `redis:8-alpine` | Health check `redis-cli ping`. Porta `127.0.0.1:6379`. |

`api` e `worker` esperam `db` e `redis` ficarem saudáveis e reiniciam em caso de falha. A imagem é voltada para desenvolvimento: roda como usuário não-root (uid 1000) e instala as dependências, incluindo ferramentas de dev (o ruff, usado pelos hooks de migration), em uma camada cacheada. Imagens de produção e deploy ficam para uma tarefa separada (veja a Fase 9). Não há Nginx.

Comandos úteis: `docker compose logs -f api`, `docker compose exec api alembic revision --autogenerate -m "..."` e `docker compose down -v`. Este último **apaga o volume do banco**.

## Regras de desenvolvimento financeiro

Obrigatórias para todo código futuro.

1. **Nunca use ponto flutuante binário para dinheiro.** Use `Decimal` no Python, `NUMERIC(p, s)` no PostgreSQL e decimais codificados como string no JSON. Todo valor carrega sua moeda, e o arredondamento é explícito (`quantize` com um modo de arredondamento nomeado).
2. **Operações de pagamento são idempotentes.** O cliente envia uma chave de idempotência, garantida por uma unique constraint no banco. O código assume retries, cliques duplos e falhas que acontecem depois de um processamento bem-sucedido.
3. **Webhooks podem chegar duplicados, atrasados ou fora de ordem.** Verifique a assinatura, deduplique pelo ID do evento e permita só transições de estado válidas.
4. **Uma chamada ao provedor pode dar timeout depois de ter dado certo.** Reconcilie; nunca repita às cegas uma movimentação de dinheiro.
5. **Nunca logue** senhas, tokens, credenciais bancárias ou payloads financeiros completos. O `hide_parameters=True` só cobre os parâmetros do SQLAlchemy: erros do banco precisam ser convertidos em erros de domínio antes de chegar ao log, e o código da aplicação segue a mesma regra.
6. **Timestamps sempre com fuso horário e armazenados em UTC.** Datas de calendário (ex.: vencimento) são `DATE`, não timestamp, e são interpretadas no fuso IANA do usuário.
7. **Nada de criptografia própria, e nunca armazene credenciais bancárias.**

## Limitações conhecidas

- As dependências usam versão mínima (`>=`) sem lock file, então os builds não são totalmente reproduzíveis. Adicionar um lock (ex.: `uv lock` ou `pip-compile --generate-hashes`) antes de CI e produção; planejado para a Fase 1.
- `/api/health` não exige autenticação e acessa banco e Redis. Antes de um deploy público, aplicar rate limit no reverse proxy ou separá-lo em liveness pública e readiness interna (Fase 9).
- O serviço `api` do Compose leva cerca de 10s para parar e termina com código 137: o comando roda via `sh -c`, que não repassa o SIGTERM ao uvicorn. Não afeta o funcionamento em desenvolvimento.

## Roadmap até o MVP

> **Estado atual:** Fundação técnica concluída.\
> **Próximo marco:** Identidade e autenticação.\
> **MVP:** não concluído.

Este roadmap é compartilhado com o `PrismaFi-Frontend`: as fases e os marcos são os mesmos nos dois repositórios. Aqui ficam os itens de **backend** (domínio, API, banco, integrações, workers, segurança, pagamentos e reconciliação). Os itens de interface estão no README do frontend.

Toda fase segue as [Regras de desenvolvimento financeiro](#regras-de-desenvolvimento-financeiro).

### Definição do MVP

O MVP está concluído quando um usuário novo consegue, de forma confiável:

```text
Criar conta → Entrar → Acessar o PrismaFi → Conectar uma instituição financeira
→ Ver contas bancárias, saldos e transações → Cadastrar uma obrigação financeira
→ Vê-la no dashboard → Escolher pagar → Selecionar uma conta de origem elegível
→ Iniciar o pagamento → Autorizá-lo no banco → Acompanhar o resultado no PrismaFi
```

Com eventos de auditoria registrados para as ações financeiras críticas. O MVP **não** precisa suportar todos os bancos, todos os meios de pagamento nem todas as capacidades do Open Finance. O objetivo é provar a proposta de valor completa com o menor produto seguro e útil.

### Visão geral das fases

| Fase | Marco | Status |
|---|---|---|
| 0 | Fundação técnica | Concluída |
| 1 | Identidade e autenticação | **Próxima** |
| 2 | Shell da aplicação e design system | Planejada |
| 3 | Integração com provedor de Open Finance | Planejada |
| 4 | Contas bancárias, saldos e transações | Planejada |
| 5 | Contas a pagar e obrigações financeiras | Planejada |
| 6 | Dashboard financeiro | Planejada |
| 7 | Iniciação de pagamentos | Planejada |
| 8 | Notificações e confiabilidade operacional | Planejada |
| 9 | Hardening do MVP | Planejada |
| 10 | Lançamento do MVP | Planejada |

### Fase 0 — Fundação técnica

**Status: concluída.** Itens verificados no repositório; a execução da stack foi confirmada localmente.

- [x] Aplicação FastAPI com lifespan (fecha engine e Redis) e handler de erros que não vaza detalhes internos
- [x] Configuração tipada via pydantic-settings, com padrão seguro (`ENVIRONMENT=production`)
- [x] SQLAlchemy 2 async + asyncpg, `Base` com convenção de nomes e `hide_parameters=True`
- [x] Alembic configurado (env async, URL vinda das settings, hooks do ruff)
- [x] Cliente Redis async
- [x] Broker Dramatiq + serviço `worker` (sem actors ainda)
- [x] `GET /api/health` (readiness de banco e Redis) e documentação OpenAPI em desenvolvimento
- [x] Docker Compose (api, worker, PostgreSQL 18, Redis 8): stack executada localmente, `alembic upgrade head` (ainda sem revisões) e `/api/health` retornando 200
- [x] Pytest, Ruff e mypy strict
- [x] Regras financeiras e de segurança documentadas

### Fase 1 — Identidade e autenticação

**Objetivo:** estabelecer a fundação de identidade segura do PrismaFi.\
**Entrega conjunta:** o usuário cria conta, entra, gerencia o perfil e as sessões ativas, e sai.

Preparação (antes do primeiro domínio):

- [ ] CI no GitHub Actions: `ruff check`, `ruff format --check`, `mypy`, `pytest`
- [ ] Lock file de dependências usado no Docker e no CI
- [ ] Convenções de modelo: chaves primárias UUID, `created_at`/`updated_at` com fuso (UTC), session factory e `get_session`, uma transação por request
- [ ] Formato padrão de erro da API (`detail` + código estável) documentado no OpenAPI

Domínio e API:

- [ ] Módulo `users`: model de usuário (com fuso horário IANA), e-mail normalizado (minúsculas, sem espaços) e único no banco. Sessões e tokens pertencem ao módulo `auth`
- [ ] Hash de senha com Argon2id usando biblioteca consolidada (sem criptografia própria)
- [ ] `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`; os demais fluxos de autenticação (sessões, verificação de e-mail, recuperação de senha) também ficam sob `/api/v1/auth/`
- [ ] Access token de curta duração (~15 min) enviado no header `Authorization`
- [ ] Refresh token opaco em cookie `HttpOnly`, `Secure`, `SameSite=Strict`, restrito ao path de auth
- [ ] Sessões persistidas no banco, com o refresh token guardado só como hash
- [ ] Rotação do refresh token a cada uso, atômica (`UPDATE ... WHERE token_hash = :antigo AND revoked_at IS NULL RETURNING`). Se o `UPDATE` não encontrar linha, o token é consultado: se foi rotacionado há poucos segundos (janela de tolerância), a requisição é aceita como renovação concorrente da mesma sessão (duas abas ao mesmo tempo) e recebe um novo access token; fora da janela, é reuso e a família de sessões é revogada. O tratamento do cookie nesse caso é definido na implementação
- [ ] Access token carrega o ID da sessão, e a sessão é verificada como ativa a cada request (no mínimo nos endpoints de pagamento), para que a revogação tenha efeito imediato
- [ ] Revogação de sessão: logout, logout de todos os dispositivos, listagem das sessões ativas
- [ ] `GET /api/v1/users/me` e atualização do perfil
- [ ] Dependencies de autenticação (`current_user`) e base de autorização: todo recurso é filtrado pelo dono
- [ ] Rate limit em login, cadastro, refresh e recuperação de senha (Redis, por IP e por conta)
- [ ] Respostas que não revelam se um e-mail está cadastrado
- [ ] Tabela de eventos de auditoria de identidade e segurança (append-only, do módulo `auth`): cadastro, login, falha de login, reuso de refresh detectado, logout, troca e recuperação de senha
- [ ] Envio de e-mail transacional por um provedor externo (função simples no módulo `auth`, sem interface)
- [ ] Verificação de e-mail e recuperação de senha (tokens de uso único, com expiração e guardados como hash)
- [ ] Testes: fluxos felizes, tokens expirados, reuso de refresh, rate limit e isolamento entre usuários (IDOR)

Decisões de segurança desta fase (detalhar e registrar antes de implementar):

| Decisão | Proposta | Motivo |
|---|---|---|
| Transporte do access token | Header `Authorization`, mantido só em memória no frontend | Não fica acessível em storage persistente e não sofre CSRF |
| Transporte do refresh token | Cookie `HttpOnly` + `Secure` + `SameSite=Strict`, com path restrito | Inacessível a JavaScript; a mesma origem dispensa CORS |
| Armazenamento | Só o hash do refresh token no banco | Um vazamento do banco não expõe sessões válidas |
| 2FA / passkeys | Pós-MVP | A autorização de pagamento acontece no banco do usuário (autenticação forte do próprio banco); 2FA no PrismaFi entra no endurecimento seguinte |

### Fase 2 — Shell da aplicação e design system

**Objetivo:** criar a experiência autenticada real do PrismaFi.\
**Entrega conjunta:** layout autenticado navegável, com os estados de carregamento, vazio e erro padronizados.

Esta fase é principalmente de frontend. No backend:

- [ ] Avaliação técnica do provedor de Open Finance iniciada em paralelo (pré-requisito da Fase 3)

### Fase 3 — Integração com provedor de Open Finance

**Objetivo:** permitir que o usuário conecte uma instituição financeira real.\
**Entrega conjunta:** o usuário conecta pelo menos uma instituição suportada e vê o status da conexão.

Avaliação do provedor (antes de implementar, com documento de decisão):

- [ ] Comparar provedores regulados capazes de oferecer dados via Open Finance Brasil **e** iniciação de pagamento Pix (ex.: agregadores como Pluggy e Belvo, ou iniciadores de pagamento autorizados)
- [ ] Critérios: cobertura de instituições, iniciação de pagamento disponível, sandbox, webhooks (assinatura, retries), suporte a chave de idempotência, modelo de preço, SLA, segurança e situação regulatória
- [ ] Registrar a decisão e as limitações aceitas

Implementação:

- [ ] Cliente do provedor escolhido em `app/integrations/<provedor>/` (dados e, se for o mesmo provedor, iniciação de pagamento), convertendo payloads para tipos do PrismaFi já na fronteira
- [ ] Cliente httpx com timeouts explícitos, retries só em operações idempotentes, sem logar payloads sensíveis
- [ ] Início da conexão e tratamento do consentimento
- [ ] Callback de retorno validado (state anti-CSRF, vinculado à sessão do usuário)
- [ ] Persistência de instituições (metadados), conexões e consentimentos, com status e expiração
- [ ] Reconexão e remoção de conexão
- [ ] Endpoint de webhooks: autenticação conforme o provedor (assinatura, segredo compartilhado ou allowlist de IP); o evento é persistido com unique constraint (provedor, ID do evento) e commitado, só então enfileirado no worker e respondido com 2xx
- [ ] Webhook tratado só como notificação: o worker consulta o estado real do recurso na API do provedor antes de qualquer transição
- [ ] Varredura periódica que reenfileira eventos persistidos e ainda não processados
- [ ] Mapeamento dos erros do provedor para estados de conexão compreensíveis
- [ ] Nunca armazenar credenciais bancárias; tokens do provedor só se forem necessários, e protegidos

### Fase 4 — Contas bancárias, saldos e transações

**Objetivo:** entregar a primeira grande proposta de valor: uma visão financeira única.\
**Entrega conjunta:** o usuário vê suas contas, saldos e o histórico de transações sincronizados.

- [ ] Models de conta bancária (metadados, tipo, moeda), saldo e transação, com `NUMERIC` + moeda
- [ ] Identificadores do provedor guardados com unique constraint (deduplicação)
- [ ] Jobs de sincronização no Dramatiq: carga inicial + incremental, idempotentes
- [ ] Estado de sincronização por conexão (`última sincronização`, `em andamento`, `falhou`) exposto na API
- [ ] Tratamento de falhas de sincronização com retry e backoff, sem duplicar dados
- [ ] Reconciliação de transações alteradas ou removidas pelo provedor
- [ ] Paginação por cursor (convenção definida aqui, com a primeira lista real), com filtros por conta e período
- [ ] Tipo monetário padrão no schema da API: valor como string decimal + moeda (`BRL`)
- [ ] Saldo consolidado e totais por instituição calculados no backend e devolvidos como string decimal
- [ ] Índices para as queries de listagem
- [ ] Autorização: o usuário só acessa contas das suas próprias conexões (testes de IDOR)

### Fase 5 — Contas a pagar e obrigações financeiras

**Objetivo:** o PrismaFi começa a responder "o que eu preciso pagar?".\
**Entrega conjunta:** o usuário cadastra, edita e acompanha suas obrigações, incluindo as próximas e as vencidas.

- [ ] Modelagem do domínio antes do código (obrigação, vencimento, valor, status, recorrência, vínculo com pagamento)
- [ ] Cadastro manual: título, descrição, valor (`Decimal`), vencimento (`DATE`) e recorrência opcional (mensal no MVP)
- [ ] Dados de pagamento da obrigação no formato suportado pelo pagamento do MVP (ex.: chave Pix ou código Pix copia e cola)
- [ ] Status pago / não pago, com marcação manual
- [ ] Consultas de obrigações próximas e vencidas (vencida = data de vencimento anterior à data de hoje no fuso IANA do usuário)
- [ ] CRUD com autorização por dono e testes

### Fase 6 — Dashboard financeiro

**Objetivo:** oferecer uma visão consolidada útil antes de introduzir pagamentos.\
**Entrega conjunta:** o dashboard responde "quanto eu tenho, onde está, o que aconteceu, o que vence e o que está atrasado".

- [ ] Endpoint de resumo (`/api/v1/dashboard/summary`) só se compor os endpoints existentes no frontend se mostrar lento ou repetitivo
- [ ] Saldo consolidado calculado no backend com `Decimal`, em BRL
- [ ] Queries de resumo com índices adequados e sem N+1

### Fase 7 — Iniciação de pagamentos

**Objetivo:** permitir pagar uma obrigação elegível a partir de uma conta escolhida pelo usuário, **sem o PrismaFi ter a custódia dos recursos**.\
**Entrega conjunta:** o usuário inicia um pagamento, autoriza no banco e acompanha o resultado no PrismaFi.

```text
Usuário → PrismaFi → Provedor de iniciação de pagamento / Open Finance
        → Instituição financeira do usuário → Autorização → Rede de pagamento (Pix)
```

Escopo do MVP: **Pix via iniciação de pagamento**, confirmado na avaliação do provedor (Fase 3). Boleto e outros meios ficam para depois do MVP.

Domínio (modelar antes de implementar):

- [ ] `Payment` com máquina de estados explícita e transições validadas no domínio
- [ ] `PaymentEvent` append-only: toda transição registra origem (usuário, provedor, webhook, reconciliação), horário e motivo. É a trilha de auditoria dos pagamentos (não é duplicada na tabela de auditoria do `auth`)
- [ ] Tentativas e autorizações (`PaymentAttempt` / `PaymentAuthorization`) só se o fluxo do provedor exigir

```text
CREATED → AUTHORIZATION_PENDING → AUTHORIZED → PROCESSING → COMPLETED
   │              │                    │            │
   └──────────────┴──→ CANCELLED / EXPIRED / FAILED ←┘
                                                    │
      UNKNOWN (timeout / resposta ambígua) → reconciliação → estado real
```

| De | Para | Origem |
|---|---|---|
| `CREATED` | `AUTHORIZATION_PENDING` | Provedor aceitou a criação |
| `AUTHORIZATION_PENDING` | `AUTHORIZED`, `CANCELLED`, `EXPIRED`, `FAILED` | Retorno do banco, webhook ou reconciliação |
| `AUTHORIZED` | `PROCESSING`, `FAILED` | Provedor |
| `PROCESSING` | `COMPLETED`, `FAILED` | Provedor, webhook ou reconciliação |
| Qualquer estado não final que chamou o provedor | `UNKNOWN` | Timeout ou resposta ambígua |
| `UNKNOWN` | Estado real informado pelo provedor | Reconciliação |

Estados finais: `COMPLETED`, `FAILED`, `CANCELLED` e `EXPIRED`. Transições fora da tabela são rejeitadas, então eventos atrasados não alteram um estado final. Devolução / estorno Pix: pós-MVP.

Regras obrigatórias:

- [ ] Valores em `Decimal` / `NUMERIC`, nunca `float`
- [ ] Criação idempotente: header `Idempotency-Key` + unique constraint (usuário, chave), guardando o hash do corpo da requisição. Mesma chave e mesmo corpo retornam o mesmo pagamento; mesma chave com corpo diferente retorna 422; mesma chave ainda em processamento retorna 409 ou o estado atual
- [ ] Chave de idempotência enviada ao provedor, derivada do `Payment.id` e reutilizada em toda nova tentativa; sem ela, a criação no provedor não é refeita automaticamente
- [ ] O pagamento é persistido (`CREATED`) e commitado **antes** de chamar o provedor; a chamada acontece fora de transação e de lock; o resultado é aplicado em uma nova transação curta
- [ ] Proteção contra clique duplo, retry HTTP, retry do frontend, retry do provedor e timeout de rede
- [ ] Bloqueio de linha (`SELECT ... FOR UPDATE`) ou controle de versão nas transições concorrentes
- [ ] Webhooks: assinatura verificada, deduplicação, eventos fora de ordem não fazem o estado regredir
- [ ] Timeout do provedor leva a `UNKNOWN`, **não** a `FAILED`; um job de reconciliação consulta o provedor com backoff limitado até chegar a um estado final e, esgotadas as tentativas, escala para o procedimento manual
- [ ] Validação de elegibilidade: a conta de origem pertence ao usuário e suporta iniciação; valor e destinatário válidos
- [ ] Vínculo entre pagamento concluído e obrigação: `payments` chama o service de `obligations` para marcá-la como paga
- [ ] Nunca logar credenciais, tokens ou payloads completos do provedor
- [ ] Testes de concorrência, idempotência, webhooks duplicados/fora de ordem e timeout

### Fase 8 — Notificações e confiabilidade operacional

**Objetivo:** garantir que o usuário entenda os eventos financeiros importantes e que a plataforma se recupere de falhas.\
**Entrega conjunta:** avisos de vencimento, conexão expirada e resultado de pagamento; falhas de jobs visíveis e recuperáveis.

- [ ] Eventos do MVP: obrigação próxima do vencimento, obrigação vencida, conexão expirada, pagamento concluído, pagamento com falha, pagamento exigindo atenção
- [ ] Model de notificação só se a interface precisar de histórico; senão, os estados do domínio já bastam
- [ ] E-mails dessas notificações, reutilizando o envio criado na Fase 1
- [ ] Agendamento periódico (lembretes de vencimento, expiração de consentimento): decisão explícita, já que o Dramatiq não tem scheduler nativo
- [ ] Política de retry e tratamento de jobs que falharam (dead letter) com visibilidade operacional

### Fase 9 — Hardening do MVP

**Objetivo:** estabilizar antes de declarar o MVP concluído.\
**Entrega conjunta:** revisão de segurança concluída, ambiente de produção pronto e caminhos críticos cobertos por testes.

Segurança e dados:

- [ ] Revisão de segurança completa (autenticação, autorização, IDOR, mass assignment, rate limit)
- [ ] Revisão de constraints, índices e limites de transação
- [ ] Verificação de idempotência, webhooks e concorrência de ponta a ponta
- [ ] Revisão das migrations (reversíveis e seguras com dados existentes)
- [ ] Auditoria: cobertura dos eventos críticos e retenção definida
- [ ] LGPD: política de privacidade, base legal, retenção de dados e exclusão de conta

Operação:

- [ ] Logs estruturados (JSON) sem dados sensíveis, com ID de correlação por request
- [ ] Health checks separados: liveness pública e readiness interna
- [ ] Rastreamento de erros (error tracking) e métricas básicas
- [ ] Estratégia de ambientes (staging e produção), HTTPS e gestão de segredos
- [ ] Imagem Docker de produção (sem ferramentas de dev, sem `--reload`, encaminhamento correto de sinais)
- [ ] Backup do PostgreSQL com restauração testada; requisito de persistência do Redis definido
- [ ] CD com deploy e estratégia de rollback

### Fase 10 — Lançamento do MVP

**Objetivo:** validar a jornada principal com usuários reais.\
**Entrega conjunta:** a jornada da [Definição do MVP](#definição-do-mvp) funciona de forma confiável em produção.

- [ ] Jornada completa testada de ponta a ponta no ambiente de produção (com o provedor em produção)
- [ ] Monitoramento ativo dos pagamentos e das sincronizações nas primeiras semanas
- [ ] Procedimento operacional para pagamentos em `UNKNOWN` e conexões com falha

### Pós-MVP

Fora do caminho crítico; reavaliar depois do lançamento:

- 2FA (TOTP) e passkeys / WebAuthn
- Boleto e outros meios de pagamento além do Pix
- Detecção automática de contas a pagar e de assinaturas
- Busca textual em transações
- Devolução / estorno de pagamentos Pix
- Múltiplos provedores de Open Finance
- Análises financeiras avançadas, recomendações e assistente com IA
- Investimentos, crédito e empréstimos
- Múltiplas moedas
- Contas empresariais, permissões de equipe e integrações contábeis / ERP
- Regras de automação e personalização avançada de notificações
- Aplicativos móveis nativos
