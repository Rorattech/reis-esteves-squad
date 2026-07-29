# Roadmap do MVP — Squad Digital | Reis Esteves Advocacia

> Copiloto jurídico com **revisão humana obrigatória**.

Oito fases sequenciais, da fundação ao piloto interno. Cada passo traz o objetivo, o prompt exato
para colar no Claude Code e o que verificar depois.

## Entrega vertical obrigatória

Nenhuma fase fecha só com backend. Cada capacidade sai como fatia completa —
`domínio · tenant/RBAC · API · LangGraph · interface · revisão humana · auditoria · testes`.
Sem tela, o advogado não revisa a triagem, não aprova fonte, não valida estratégia nem edita a
minuta — e o humano no loop deixa de existir na prática.

## Índice

- [Fase 1 — Fundação & Infraestrutura](#fase-1--fundação--infraestrutura) · Semanas 1–2 · 6 passos (backend)
- [Fase 1½ — Auditoria da Fase 1](#fase-1½--auditoria-da-fase-1) · Antes de qualquer código novo · 2 passos (1 backend + 1 interface)
- [F0 — Fundação do frontend](#f0--fundação-do-frontend) · Antes da Fase 2 · casca da aplicação · 1 passo (interface)
- [Fase 2 — Intake e roteamento](#fase-2--intake-e-roteamento) · Módulo LangGraph: intake · 6 passos (4 backend + 2 interface)
- [Fase 3 — Evidências digitais](#fase-3--evidências-digitais) · Módulo LangGraph: evidence · 5 passos (3 backend + 2 interface)
- [Fase 4 — Pesquisa jurídica verificável](#fase-4--pesquisa-jurídica-verificável) · Módulo LangGraph: research · 4 passos (3 backend + 1 interface)
- [Fase 5 — Estratégia jurídica assistida](#fase-5--estratégia-jurídica-assistida) · Módulo LangGraph: strategy · 3 passos (2 backend + 1 interface)
- [Fase 6 — Produção da peça jurídica](#fase-6--produção-da-peça-jurídica) · Módulo LangGraph: drafting · 3 passos (2 backend + 1 interface)
- [Fase 7 — Qualidade e aprendizado controlado](#fase-7--qualidade-e-aprendizado-controlado) · Módulo LangGraph: review · 3 passos (2 backend + 1 interface)
- [Fase 8 — End-to-end, segurança e piloto interno](#fase-8--end-to-end-segurança-e-piloto-interno) · Fechamento do MVP · 3 passos (2 backend + 1 interface)

Total: **36 passos** — 25 de backend/orquestração e 11 de interface.

---

## Fase 1 — Fundação & Infraestrutura

*Semanas 1–2*

**Objetivo da fase:** Levantar o monorepo, os containers, o banco multi-tenant com RLS, a autenticação JWT e o CaseState. Sem essa base, nenhum módulo do grafo funciona.

### Criar o repositório e a estrutura de pastas

`Terminal · manual` · trilha: **Backend · orquestração**

**Objetivo:** Antes de abrir o Claude Code, crie a estrutura base manualmente. Isso garante que o Claude Code já encontre o projeto organizado ao iniciar.

**Comandos no terminal**

```md
mkdir squad-digital && cd squad-digital
git init
mkdir -p backend/app/{api,services,models,schemas,middleware}
mkdir -p orchestrator/{agents,modules,prompts}
mkdir -p prompts/{intake,evidence,research,strategy,drafting,review}
mkdir -p frontend/src/{app,components,lib}
mkdir -p infra n8n docs/adr .claude
touch CLAUDE.md .env.example .gitignore
touch docs/architecture.md
```

**Verificar depois**

- [ ] <b>Copie o CLAUDE.md e o architecture.md para a raiz.</b> O Claude Code lê esses arquivos automaticamente ao iniciar.
- [ ] <b>Crie o .claude/settings.json com as permissões definidas.</b> Impede que o Claude Code faça push ou sobrescreva o .env.
- [ ] <b>Adicione ao .gitignore:</b> .env, __pycache__, .venv, node_modules, *.pem, *.key. Nunca commitar segredos.

### Docker Compose completo

`infra/docker-compose.yml` · trilha: **Backend · orquestração**

**Objetivo:** Abra o Claude Code na raiz do projeto e use este prompt exato.

**Prompt para o Claude Code**

```text
Leia o CLAUDE.md e o docs/architecture.md.
Crie o arquivo infra/docker-compose.yml com os seguintes serviços:
- postgres:16 com pgvector, porta 5432, volume persistente
- redis:7-alpine, porta 6379
- n8n:latest, porta 5678, variáveis de env do .env.example
- backend FastAPI (Dockerfile em backend/), porta 8000, hot-reload
- frontend Next.js (Dockerfile em frontend/), porta 3000
Todos os serviços devem estar na mesma rede interna "squad-net".
Crie também o backend/Dockerfile e frontend/Dockerfile básicos.
```

**Verificar depois**

- [ ] <b>Valide que o pgvector está habilitado no postgres.</b> CREATE EXTENSION IF NOT EXISTS vector; deve estar no init.sql.
- [ ] <b>Teste com docker compose up --build.</b> Todos os serviços devem subir sem erro antes de avançar.
- [ ] <b>O n8n deve responder em localhost:5678.</b> Faça o login inicial e salve as credenciais no .env.

### Banco de dados base + Alembic

`backend/app/models/` · trilha: **Backend · orquestração**

**Objetivo:** Com o Docker rodando, peça ao Claude Code para criar os modelos e a primeira migration.

**Prompt para o Claude Code**

```text
Leia o CLAUDE.md e o docs/architecture.md.
Crie os modelos SQLAlchemy em backend/app/models/ para as tabelas:
- tenants (id, name, slug, created_at)
- users (id, tenant_id FK, email, hashed_password, role, created_at)
- cases (id, tenant_id FK, user_id FK, platform, fraud_type,
         urgency, status, created_at, updated_at)
- audit_logs (id, tenant_id FK, case_id FK, actor_id, action,
              input_hash, output_hash, agent_name, model_used, created_at)
Todas as tabelas devem ter tenant_id UUID NOT NULL.
Habilite RLS em todas as tabelas com política de isolamento por tenant.
Configure Alembic e gere a migration inicial.
```

**Verificar depois**

- [ ] <b>Rode alembic upgrade head dentro do container backend.</b> Confirme que as tabelas foram criadas no PostgreSQL.
- [ ] <b>Verifique o RLS com \d+ cases no psql.</b> A política tenant_isolation deve aparecer na listagem.
- [ ] <b>Crie um tenant e um user de teste via psql.</b> Uma query sem SET app.current_tenant deve retornar 0 linhas.

### Autenticação JWT

`backend/app/api/auth.py` · trilha: **Backend · orquestração**

**Objetivo:** Implemente o sistema de autenticação. Este é o único ponto de entrada do sistema.

**Prompt para o Claude Code**

```text
Leia o CLAUDE.md.
Implemente autenticação JWT no FastAPI em backend/app/api/auth.py:
- POST /api/v1/auth/register (cria tenant + user admin)
- POST /api/v1/auth/login (retorna access_token 15min + refresh_token 7d)
- POST /api/v1/auth/refresh (renova access_token)
- GET /api/v1/auth/me (retorna user autenticado)
Crie o middleware em backend/app/middleware/tenant.py que:
- Extrai tenant_id do JWT em cada request
- Injeta SET app.current_tenant na sessão do banco
- Bloqueia requests sem tenant_id válido com 403
Use bcrypt para hash de senha. Segredos via variáveis de ambiente.
```

**Verificar depois**

- [ ] <b>Registre um tenant, faça login e acesse /me.</b> O token deve conter tenant_id, user_id e role no payload.
- [ ] <b>Confirme que o middleware injeta o tenant_id no banco.</b> Use um log temporário e remova depois.
- [ ] <b>Nunca hardcode SECRET_KEY.</b> Deve vir de JWT_SECRET_KEY no .env — o settings.json garante que o Claude Code não sobrescreva.

### CaseState e schemas Pydantic

`orchestrator/state.py` · trilha: **Backend · orquestração**

**Objetivo:** O arquivo mais crítico da Fase 1. Tudo que os agentes produzem passa por aqui.

**Prompt para o Claude Code**

```text
Leia o CLAUDE.md e o docs/architecture.md com atenção ao CaseState.
Crie orchestrator/state.py com o TypedDict CaseState contendo:
- case_id: str
- tenant_id: str
- platform: str (Meta, Shopee, MercadoLivre, WhatsApp, etc.)
- fraud_type: str
- urgency: Literal["low","medium","high","critical"]
- documents_requested: list[str]
- evidence_inventory: list[EvidenceItem]
- legal_sources: list[LegalSource]
- strategy_memo: Optional[StrategyMemo]
- draft_petition: Optional[DraftPetition]
- human_approval_required: bool
- human_approval_status: Literal["pending","approved","rejected","na"]
- audit_trail: list[AuditEntry]
- current_module: str
- status: Literal["active","suspended","completed","error"]
Crie também os schemas Pydantic em backend/app/schemas/case.py
para os endpoints da API (CaseCreate, CaseResponse, CaseUpdate).
```

**Verificar depois**

- [ ] <b>Valide o CaseState em um teste unitário simples.</b> pytest tests/test_state.py deve passar antes de avançar.
- [ ] <b>LegalSource precisa de:</b> source_type, title, url, excerpt, verified (bool), hallucination_risk (bool). Nunca retornar fonte sem esses campos.
- [ ] <b>AuditEntry precisa de:</b> timestamp, agent_name, model_used, input_hash, output_hash, actor_id — SHA-256 para rastreabilidade.

### Validação final da Fase 1

`Checklist de saída` · trilha: **Backend · orquestração**

**Objetivo:** Antes de avançar para a Fase 2, valide cada item abaixo. Não pule esta etapa.

**Comandos de verificação**

```md
# Rode todos os testes
docker compose exec backend pytest tests/ -v

# Verifique as tabelas no banco
docker compose exec postgres psql -U postgres -d squaddigital -c "\dt"

# Confirme RLS ativo
docker compose exec postgres psql -U postgres -d squaddigital \
  -c "SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public';"

# Teste autenticação end-to-end
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Reis Esteves","email":"admin@reisesteves.com","password":"Test@123"}'
```

**Verificar depois**

- [ ] docker compose up sobe todos os 5 serviços sem erro.
- [ ] Tabelas criadas com tenant_id e RLS ativo em todas.
- [ ] Login retorna JWT com tenant_id no payload.
- [ ] Middleware bloqueia request sem token com 403.
- [ ] CaseState importa sem erro e os testes unitários passam.
- [ ] n8n acessível em localhost:5678.

---

## Fase 1½ — Auditoria da Fase 1

*Antes de qualquer código novo*

**Objetivo da fase:** Antes de começar a Fase 2, peça ao Claude Code para inspecionar o que já existe e identificar lacunas. Isso evita que ele recrie estruturas ou invente nomes de tabelas, modelos e módulos.

### Auditoria técnica do que já existe

`docs/phase_1_audit.md` · trilha: **Backend · orquestração**

**Objetivo:** Relatório de estado real do repositório, sem alterar nenhum arquivo.

**Prompt para o Claude Code**

```text
Faça uma auditoria técnica da Fase 1 deste repositório antes de qualquer implementação.

Leia integralmente:
- CLAUDE.md
- docs/architecture.md
- pyproject.toml
- docker-compose.yml
- migrations existentes
- estrutura de app/, orchestrator/, prompts/, tests/ e infraestrutura disponível

Objetivo: confirmar se a Fase 1 do MVP está efetivamente concluída para suportar os módulos posteriores do Squad Digital.

Verifique especificamente:
1. Ambiente Docker funcional e serviços necessários.
2. Configuração de banco de dados e migrations.
3. Autenticação JWT e RBAC.
4. Multi-tenancy: tenant_id presente nas entidades necessárias e isolamento garantido.
5. RLS configurado no banco, se PostgreSQL estiver sendo utilizado.
6. audit_log com actor_id, tenant_id, ação, input_hash, output_hash, metadados e timestamps.
7. CaseState em orchestrator/state.py.
8. Estrutura LangGraph sem uso de LangChain como orquestrador.
9. Carregamento versionado de prompts a partir de prompts/.
10. Cobertura mínima de testes para autenticação, tenancy e auditoria.

Não altere nenhum arquivo ainda.

Entregue um relatório em docs/phase_1_audit.md contendo:
- itens concluídos;
- itens parcialmente concluídos;
- lacunas bloqueantes;
- arquivos envolvidos;
- riscos técnicos;
- plano mínimo de correção, em ordem de prioridade.

Não invente nomes de entidades, tabelas ou funções: extraia-os exclusivamente do repositório.
```

**Verificar depois**

- [ ] Existe docs/phase_1_audit.md.
- [ ] O projeto sobe localmente sem erro.
- [ ] Um usuário de um tenant não consegue consultar dados de outro tenant.
- [ ] Há teste automatizado demonstrando esse isolamento.
- [ ] Toda ação relevante deixa registro no audit_log.
- [ ] CaseState existe e é a única estrutura de estado compartilhada entre os módulos.

> Só avance se não houver lacuna bloqueante em autenticação, isolamento por tenant, auditoria ou migrations.

### Diretriz de entrega vertical no CLAUDE.md

`CLAUDE.md · regra de projeto` · trilha: **Interface**

**Objetivo:** Antes de seguir para as próximas fases, grave no CLAUDE.md a regra que impede uma fase de ser fechada só com backend. É o que faz o Claude Code entregar a tela junto com o endpoint em cada etapa.

**Bloco a acrescentar ao CLAUDE.md**

```md
## Entrega vertical obrigatória

Toda fase funcional do Squad Digital deve ser implementada como uma fatia vertical completa.

Uma fase não estará concluída se entregar apenas backend, banco de dados, API, LangGraph ou prompts. Cada capacidade voltada ao usuário deve incluir, quando aplicável:

1. domínio, migrations e persistência;
2. regras de isolamento por tenant, RBAC e RLS;
3. API autenticada;
4. orquestração LangGraph;
5. interface frontend correspondente;
6. estados explícitos de carregamento, vazio, erro e sucesso;
7. revisão humana obrigatória nos pontos de decisão jurídica;
8. audit_log rastreável;
9. testes de backend, API e frontend;
10. documentação do fluxo.

O frontend é uma interface de copilot jurídico. Ele não pode:
- indicar que uma decisão jurídica foi tomada autonomamente;
- permitir protocolo judicial;
- ocultar pendências, incertezas ou fontes não verificadas;
- aprovar automaticamente estratégia, fonte, peça ou conclusão jurídica.

Toda ação humana de aprovar, rejeitar, editar, corrigir ou devolver uma etapa deve gerar auditoria.
```

**Verificar depois**

- [ ] A seção está no CLAUDE.md e o Claude Code passa a citá-la ao planejar cada fase.
- [ ] Nenhuma fase seguinte é dada como concluída sem a tela correspondente.
- [ ] A definição de pronto por fase é usada como checklist de fechamento.

---

## F0 — Fundação do frontend

*Antes da Fase 2 · casca da aplicação*

**Objetivo da fase:** Você não precisa construir todas as telas antes do Intake, mas precisa da casca: login, sessão, layout autenticado, navegação, cliente HTTP com JWT e os componentes reutilizáveis de estado e de revisão humana que todas as fases seguintes vão consumir.

### F0.1 — Auditar ou criar a fundação do frontend

`docs/frontend_foundation_audit.md` · trilha: **Interface**

**Objetivo:** Descobrir o que já existe antes de escrever tela: framework, gerenciador de pacotes, rotas, autenticação e padrão de estilo. Depois implementar apenas a fundação mínima — sem criar um segundo frontend nem migrar framework.

**Estrutura visual mínima**

```text
Aplicação
├── Login
├── Layout autenticado
│   ├── Barra lateral
│   │   ├── Casos
│   │   ├── Pesquisa jurídica
│   │   ├── Revisões pendentes
│   │   └── Configurações
│   ├── Cabeçalho
│   │   ├── Tenant/escritório atual
│   │   ├── Usuário autenticado
│   │   └── Notificações
│   └── Conteúdo principal
├── Lista de casos
└── Página de caso
    ├── Visão geral
    ├── Intake
    ├── Evidências
    ├── Pesquisa
    ├── Estratégia
    ├── Minuta
    ├── Revisão
    └── Histórico
```

**Prompt para o Claude Code**

```text
Faça uma auditoria da camada frontend existente e prepare a fundação necessária para o MVP do Squad Digital.

Antes de alterar qualquer arquivo:
1. Leia integralmente CLAUDE.md.
2. Inspecione a estrutura do repositório.
3. Identifique se já existe frontend, qual framework é usado, qual gerenciador de pacotes é adotado e como ele se comunica com a API.
4. Identifique rotas, autenticação, componentes, padrões de estilo, testes e ambiente de desenvolvimento já existentes.
5. Não crie um segundo frontend nem migre framework sem necessidade justificada.

Entregue primeiro um plano curto no arquivo docs/frontend_foundation_audit.md contendo:
- estrutura frontend atual;
- stack efetivamente encontrada;
- lacunas para o MVP;
- decisões que serão preservadas;
- arquivos que serão alterados.

Depois implemente ou complete somente a fundação mínima para o MVP:

1. Layout autenticado da aplicação.
2. Proteção de rotas por sessão JWT.
3. Cliente HTTP centralizado que injeta Authorization Bearer token.
4. Não enviar tenant_id como valor confiado ao frontend: o backend deve derivá-lo do token.
5. Navegação lateral com os itens:
   - Casos
   - Pesquisa jurídica
   - Revisões pendentes
   - Configurações
6. Componente reutilizável de estado de carregamento.
7. Componente reutilizável de estado vazio.
8. Componente reutilizável de erro de API.
9. Componente reutilizável de badge de status.
10. Componente reutilizável de aviso "Revisão humana obrigatória".
11. Componente reutilizável para confirmação de ações relevantes.
12. Base para exibir histórico de auditoria sem expor hashes ou dados técnicos desnecessários ao usuário final.

Regras obrigatórias:
- Não implementar telas fictícias desconectadas da API.
- Não inventar endpoints. Descubra os endpoints existentes no backend.
- Não armazenar JWT de forma insegura se o projeto já tiver padrão de sessão definido.
- Não confiar em permissões apenas no frontend; elas devem continuar sendo verificadas no backend.
- Não incluir mecanismos de protocolo judicial.
- Implementar testes compatíveis com a stack encontrada.
- Executar os testes e documentar como subir frontend e backend localmente.

Ao final, liste os arquivos alterados, comandos executados e resultados dos testes.
```

**Verificar depois**

- [ ] Usuário não autenticado não acessa /cases ou equivalente.
- [ ] A interface não recebe nem controla o tenant_id como fonte de verdade.
- [ ] Há uma estrutura visual única, não telas desconexas.
- [ ] O projeto apresenta erro de API de maneira compreensível.
- [ ] Existe um componente explícito para “revisão humana obrigatória”.

---

## Fase 2 — Intake e roteamento

*Módulo LangGraph: intake*

**Objetivo da fase:** Permitir a criação segura de um caso e transformar um relato inicial em triagem estruturada, com classificação de urgência, plataforma, modalidade do golpe e checklist de documentos.

### 2.1 — Modelar o domínio de casos e intake

`Modelos · migrations · schemas` · trilha: **Backend · orquestração**

**Objetivo:** Criar a camada de domínio do caso jurídico, sempre ancorada em tenant_id, sem duplicar o que já existe no repositório.

**Prompt para o Claude Code**

```text
Implemente a camada de domínio necessária para a Fase 2 — Intake e Roteamento.

Antes de editar:
1. Leia CLAUDE.md, docs/architecture.md e docs/phase_1_audit.md.
2. Inspecione os modelos, schemas, migrations, convenções de nomes e testes existentes.
3. Reutilize a estrutura atual; não crie modelos ou tabelas duplicadas.

Implemente, por migration e modelos já adotados no projeto, o suporte mínimo para:

- Caso jurídico vinculado a tenant_id.
- Cliente vinculado ao tenant_id.
- Registro de intake/relato inicial.
- Classificação de área, matéria, plataforma ré e modalidade de golpe.
- Nível de urgência.
- Status do caso e status da etapa no fluxo.
- Checklist de documentos: recebido, pendente, dispensado.
- Campo para indicar necessidade de revisão humana.
- Auditoria obrigatória para criação e atualização dos dados.

Regras obrigatórias:
- tenant_id deve estar presente e ser validado em todas as operações.
- Não aceitar tenant_id do corpo da requisição quando ele puder ser derivado do token autenticado.
- Aplicar RLS conforme a convenção existente no projeto.
- Não colocar regras jurídicas ou prompts inline no Python.
- Não criar rotas de protocolo judicial, automação de envio ou decisão jurídica autônoma.
- Criar testes de isolamento entre tenants e testes de validação dos novos schemas.

Atualize, se necessário: migrations, modelos, schemas, serviços/repositórios, testes e documentação técnica da Fase 2.

Ao final, execute a suíte de testes e apresente os arquivos alterados e o resultado.
```

**Verificar depois**

- [ ] Um caso sempre pertence a exatamente um tenant_id.
- [ ] O tenant_id vem do usuário autenticado, e não de input manipulável pelo cliente.
- [ ] O checklist de documentos é persistido e auditável.
- [ ] Há migration reversível.
- [ ] Testes demonstram que um tenant não lista, altera nem acessa os casos de outro.

### 2.2 — Carregador de prompts versionados

`core/prompts.py` · trilha: **Backend · orquestração**

**Objetivo:** Montar o prompt final por composição de camadas, com validação de frontmatter, versão e hash — sem chamar LLM ainda.

**Prompt para o Claude Code**

```text
Implemente ou complete o sistema de carregamento de prompts versionados do projeto.

Antes de editar:
- Inspecione a estrutura atual de prompts e qualquer carregador existente.
- Leia CLAUDE.md e docs/architecture.md.
- Não duplique uma implementação existente.

O carregador deve montar o prompt final por composição, nesta ordem:

1. prompts/_shared/base.md
2. prompts/_shared/output_format.md
3. prompts/{squad}/_squad.md
4. prompts/{squad}/{module}/{agent}.md

Para o MVP, o squad suportado é digital.

Requisitos:
- Ler e validar o frontmatter YAML dos arquivos Markdown.
- Validar versão, squad, module e agent.
- Registrar no audit_log as versões e hashes dos prompts utilizados.
- Falhar de forma explícita se houver arquivo ausente, frontmatter inválido ou incompatibilidade de squad/módulo/agente.
- Não carregar prompt por caminho informado diretamente por usuário.
- Criar testes unitários para composição, validação, falhas e cálculo de hashes.
- Documentar a API interna do carregador.

Não implemente chamada de LLM nesta etapa; somente o carregamento confiável e auditável de prompts.
```

**Verificar depois**

- [ ] O prompt final do agente de triagem inclui as quatro camadas.
- [ ] O hash e a versão de cada prompt ficam no registro de auditoria.
- [ ] Um prompt inexistente causa erro controlado, sem fallback silencioso.
- [ ] Há testes para prompt válido e para prompt inválido.

### 2.3 — Nós coordinator e triage

`orchestrator/graphs/intake.py` · trilha: **Backend · orquestração**

**Objetivo:** Classificar plataforma, modalidade e urgência; normalizar dados; produzir checklist de documentos faltantes e definir o próximo módulo — sempre como recomendação revisável.

**Prompt para o Claude Code**

```text
Implemente os nós LangGraph da Fase 2 para o fluxo de Intake do Squad Digital.

Antes de editar:
1. Leia o CaseState real em orchestrator/state.py.
2. Inspecione como o grafo LangGraph existente é estruturado.
3. Inspecione o carregador de prompts implementado no projeto.
4. Leia os prompts:
   - prompts/digital/intake/coordinator.md
   - prompts/digital/intake/triage.md
   - prompts/_shared/base.md
   - prompts/_shared/output_format.md
   - prompts/digital/_squad.md

Implemente:
- Nó coordinator: identifica se o caso é potencialmente do Squad Digital, classifica plataforma, modalidade e urgência preliminar.
- Nó triage: normaliza dados, produz checklist de documentos faltantes e determina o próximo módulo.
- Validação estruturada da saída do modelo por schema definido no projeto.
- Estados explícitos para: concluído, bloqueado, aguardando informação e aguardando revisão humana.
- Persistência dos resultados no caso, sempre com tenant_id.
- Registro de auditoria de input, output, versões/hash dos prompts, modelo utilizado e ator.
- Nenhuma decisão deve ser final: o resultado deve ser marcado como recomendação para revisão humana.
- Casos fora do escopo digital devem ser marcados como encaminhamento, sem inventar outro fluxo.

Não use LangChain para orquestração.
Não armazene segredo, API key ou conteúdo de prompt inline.
Crie testes com stubs/mocks do provedor de LLM para:
1. caso de golpe PIX;
2. caso de marketplace;
3. caso fora do escopo digital;
4. caso com informações insuficientes;
5. isolamento entre tenants;
6. falha de validação de saída do modelo.

Atualize a documentação do fluxo e execute os testes.
```

**Verificar depois**

- [ ] Um caso de golpe no Marketplace resulta em plataforma provável, modalidade provável, urgência, checklist de documentos e encaminhamento ao módulo evidence.
- [ ] Informações insuficientes não produzem fatos inventados; o estado fica como “aguardando informação”.
- [ ] O resultado é uma recomendação revisável por humano.
- [ ] Não há chamada a LLM sem log de auditoria.

### 2.4 — API de intake e revisão humana

`backend/app/api/v1/` · trilha: **Backend · orquestração**

**Objetivo:** Expor criação de caso, checklist, execução do intake, consulta do resultado, revisão humana e histórico de auditoria — tudo com RBAC.

**Prompt para o Claude Code**

```text
Implemente a interface de API necessária para a Fase 2 — Intake e revisão humana.

Antes de editar, inspecione as convenções existentes de rotas, autenticação, RBAC, responses e tratamento de erros.

Implemente endpoints compatíveis com a arquitetura atual para:
- criar um caso e relato inicial;
- anexar ou listar o checklist de documentos;
- iniciar o fluxo de intake;
- consultar o resultado de coordenação e triagem;
- registrar revisão humana, correção ou aprovação do resultado;
- consultar o histórico de auditoria do caso, sujeito a RBAC.

Requisitos obrigatórios:
- Aplicar autenticação e RBAC.
- Derivar tenant_id da identidade autenticada.
- Nunca expor dados de outro tenant.
- Não permitir que a API aprove automaticamente uma estratégia ou peça jurídica.
- Registrar auditoria em cada mutação.
- Usar schemas de entrada e saída, com erros consistentes.
- Criar testes de API para autenticação, RBAC, isolamento de tenants e revisão humana.
- Atualizar a documentação OpenAPI ou equivalente já utilizada pelo projeto.

Execute os testes ao final.
```

**Verificar depois**

- [ ] Usuário autorizado cria e consulta somente casos do próprio escritório.
- [ ] Resultado de triagem pode ser corrigido por um advogado humano.
- [ ] A correção humana fica auditada.
- [ ] Usuário sem papel adequado não acessa auditoria ou dados de caso.

### 2.5 — Lista de casos, novo caso e detalhe

`Telas de caso` · trilha: **Interface**

**Objetivo:** A fase não termina no endpoint. Termina quando o advogado abre a lista, cria um caso e chega à página de detalhe com a linha do tempo das etapas.

**Telas desta etapa**

| Tela | Usuário faz | Resultado |
|---|---|---|
| Lista de Casos | Consulta, busca e filtra casos | Acessa somente casos do próprio tenant |
| Novo Caso | Registra cliente e relato inicial | Caso criado em estado inicial |
| Detalhe do Caso | Visualiza status e etapas | Acompanha o fluxo inteiro |

**Prompt para o Claude Code**

```text
Implemente a fatia frontend da Fase 2 para listagem e criação de casos.

Antes de editar:
1. Leia CLAUDE.md e docs/frontend_foundation_audit.md.
2. Inspecione os endpoints, schemas e permissões reais implementados para casos e intake.
3. Não invente nomes de rotas, campos, status ou payloads. Use exclusivamente o que existir no backend.

Implemente as telas:

1. Lista de casos:
   - tabela ou lista responsiva;
   - status atual;
   - cliente ou identificador permitido pelo backend;
   - modalidade/plataforma quando disponível;
   - última atualização;
   - indicador de etapa atual;
   - busca e filtros somente se houver suporte no backend;
   - estado vazio com ação "Criar caso".

2. Criação de caso:
   - formulário baseado nos schemas reais da API;
   - validação de campos no frontend sem substituir validação backend;
   - envio para endpoint autenticado;
   - feedback claro de sucesso ou erro;
   - redirecionamento para o detalhe do caso após sucesso.

3. Página de detalhe do caso:
   - cabeçalho com status;
   - linha do tempo das etapas:
     Intake → Evidências → Pesquisa → Estratégia → Minuta → Revisão;
   - etapas futuras devem aparecer bloqueadas quando ainda não estiverem liberadas;
   - não exibir informação de outros tenants;
   - não permitir alteração de status diretamente pela interface fora das ações autorizadas pelo backend.

Estados obrigatórios em cada tela:
- carregando;
- sem dados;
- erro;
- acesso negado;
- sucesso.

Crie testes de interface para:
- usuário autenticado consultando casos;
- estado vazio;
- falha de API;
- criação com validação inválida;
- criação bem-sucedida;
- tentativa de acesso a um caso indisponível para o usuário.

Execute os testes e documente os arquivos alterados.
```

**Verificar depois**

- [ ] A lista mostra apenas casos permitidos pela API autenticada.
- [ ] Ao criar um caso, o advogado é levado para a página correta.
- [ ] O sistema não permite “pular” visualmente para estratégia ou minuta.
- [ ] Mensagens de erro são úteis e não expõem stack trace.

### 2.6 — Formulário de intake e revisão da triagem

`Aba Intake · revisão humana` · trilha: **Interface**

**Objetivo:** Onde o humano no loop começa a existir de verdade: o advogado preenche o relato, executa a triagem, vê o que foi inferido e o que ficou pendente, e aprova, corrige ou devolve.

**Fluxo visual**

```text
Lista de Casos
      ↓
Novo Caso
      ↓
Formulário de Intake
      ↓
"Executar Triagem"
      ↓
Resultado estruturado
      ↓
Advogado aprova / corrige / devolve
      ↓
Caso segue para Evidências
```

**Prompt para o Claude Code**

```text
Implemente a interface frontend de Intake e revisão humana da triagem para o Squad Digital.

Antes de editar:
- Inspecione os schemas e endpoints reais de intake, coordinator, triage e revisão humana.
- Leia os estados possíveis do caso no backend e no LangGraph.
- Não invente campos jurídicos ou classificações que não existam no projeto.

Implemente na página de detalhe do caso uma aba ou seção "Intake" com:

1. Formulário de relato inicial:
   - relato livre;
   - campos estruturados que existirem no schema real;
   - plataforma envolvida;
   - modalidade do golpe;
   - valor envolvido;
   - existência de BO;
   - urgência relatada;
   - documentos já disponíveis;
   - indicação de informações desconhecidas, quando aplicável.

2. Ação "Executar triagem":
   - só disponível quando houver os dados mínimos definidos pelo backend;
   - confirmação antes de executar;
   - estado de processamento;
   - bloqueio de clique duplicado;
   - atualização do resultado após conclusão.

3. Painel de resultado da triagem:
   - escopo identificado;
   - plataforma provável;
   - modalidade provável;
   - urgência;
   - fatos extraídos;
   - informações pendentes;
   - checklist de documentos;
   - recomendação de próximo módulo;
   - aviso fixo de que a saída é assistida e requer validação humana.

4. Revisão humana:
   - botão Aprovar;
   - botão Corrigir;
   - botão Devolver para complementação;
   - campo obrigatório de justificativa quando houver correção ou devolução;
   - edição apenas dos campos permitidos pela API;
   - histórico de versões e decisões.

Regras:
- A interface não pode chamar "aprovação" se o backend não aceitar a transição.
- Não pode ocultar pendências geradas pela triagem.
- Não pode apresentar classificação como fato definitivo.
- Toda revisão deve ser visível no histórico do caso.
- Implementar testes de fluxo de aprovação, correção, devolução, falha e carregamento.

Execute os testes ao final.
```

**Verificar depois**

- [ ] O advogado vê claramente o que foi inferido e o que está pendente.
- [ ] Triagem incompleta não avança sem confirmação humana.
- [ ] “Corrigir” cria histórico, não apaga silenciosamente a saída anterior.
- [ ] O botão para Evidências só é liberado depois da transição aceita pelo backend.

---

## Fase 3 — Evidências digitais

*Módulo LangGraph: evidence*

**Objetivo da fase:** Receber documentos, extrair conteúdo quando possível, criar inventário probatório e apontar lacunas — sem alterar os arquivos originais.

### 3.1 — Upload seguro e inventário de evidências

`Armazenamento · cadeia de custódia` · trilha: **Backend · orquestração**

**Objetivo:** Guardar o original intacto, com hash de integridade, metadados, deduplicação por tenant e auditoria de acesso.

**Prompt para o Claude Code**

```text
Implemente a base de gestão de evidências da Fase 3.

Antes de editar:
- Leia a arquitetura, os modelos existentes, a estratégia de armazenamento já definida e o CaseState.
- Reutilize padrões de upload e armazenamento existentes, se houver.

Implemente suporte para:
- upload de arquivos vinculados a um caso e tenant;
- metadados de evidência: tipo, nome original, MIME type, tamanho, hash criptográfico, origem, data de recebimento e status de processamento;
- relacionamento entre evidência, caso, tenant e usuário que realizou o upload;
- inventário de evidências;
- preservação do arquivo original sem alteração;
- detecção de duplicidade por hash dentro do mesmo tenant;
- registro de cadeia de custódia simplificada: quem enviou, quando, de onde, e quais processamentos foram executados;
- auditoria integral de upload, acesso e processamento.

Regras obrigatórias:
- Validar extensão, MIME type, tamanho e conteúdo quando aplicável.
- Não permitir acesso por URL pública não autorizada.
- Não permitir acesso cruzado entre tenants.
- Não modificar o arquivo original.
- Separar arquivo original, texto extraído e artefatos derivados.
- Não implementar análise jurídica nesta etapa.
- Criar testes de autorização, isolamento por tenant, tipo inválido, arquivo duplicado e auditoria.

Atualize a documentação técnica e execute os testes.
```

**Verificar depois**

- [ ] Arquivos de um tenant não são recuperáveis por outro.
- [ ] Existe hash de integridade para cada upload.
- [ ] O arquivo original não é sobrescrito por OCR ou transcrição.
- [ ] O inventário mostra status como recebido, processando, processado ou falhou.

### 3.2 — Pipeline de OCR, transcrição e normalização

`Workers assíncronos · n8n` · trilha: **Backend · orquestração**

**Objetivo:** Extrair texto de PDFs e imagens de forma assíncrona, marcando confiança e limitações, sem tocar no original.

**Prompt para o Claude Code**

```text
Implemente o pipeline assíncrono de extração de conteúdo de evidências da Fase 3.

Antes de editar:
- Inspecione a infraestrutura existente para tarefas assíncronas, filas, workers e armazenamento.
- Caso não exista uma solução definida no repositório, proponha a menor solução compatível com a arquitetura e implemente apenas após documentar a decisão.

O pipeline deve:
1. Receber uma evidência já validada.
2. Detectar o tipo de arquivo.
3. Extrair texto de PDF nativo.
4. Executar OCR apenas quando necessário em imagens ou PDF escaneado.
5. Gerar transcrição estruturada de conversas quando aplicável.
6. Armazenar texto extraído e artefatos derivados sem alterar o original.
7. Registrar versão da ferramenta, timestamp, hash de entrada e hash da saída.
8. Atualizar o estado da evidência.
9. Registrar falhas de forma rastreável e segura.

Regras:
- Não afirmar que OCR é prova perfeita; marque incertezas e baixa confiança.
- Não classificar juridicamente nem criar fatos.
- Não enviar arquivos entre tenants.
- Não logar conteúdo sensível integral em logs de aplicação.
- Criar testes para PDF textual, imagem, arquivo inválido, falha de OCR e isolamento entre tenants.

Atualize a documentação operacional do pipeline.
```

**Verificar depois**

- [ ] Um print de WhatsApp tem texto extraído separado do original.
- [ ] O resultado informa confiança e limitações da extração.
- [ ] Falhas não apagam nem corrompem o arquivo.
- [ ] Logs técnicos não expõem dados pessoais ou conversas completas.

### 3.3 — Nós documental e specialist

`orchestrator/graphs/evidence.py` · trilha: **Backend · orquestração**

**Objetivo:** Construir o inventário probatório rastreável e a leitura técnica da plataforma, distinguindo fato, inferência e ausência de informação.

**Prompt para o Claude Code**

```text
Implemente os nós LangGraph de Evidências do Squad Digital.

Leia antes:
- CaseState;
- prompts/digital/evidence/documental.md;
- prompts/digital/evidence/specialist.md;
- estrutura de evidências e textos extraídos;
- carregador de prompts;
- convenções de auditoria e revisão humana.

Implemente:
1. Nó documental:
   - cria inventário de provas;
   - identifica documentos, prints, comprovantes, URLs e lacunas;
   - relaciona cada achado com a evidência de origem;
   - não inventa conteúdo ausente.

2. Nó specialist:
   - contextualiza tecnicamente a evidência em relação à plataforma e modalidade do golpe;
   - aponta hipóteses e recomendações de preservação;
   - diferencia fato extraído, inferência técnica e informação pendente.

A saída estruturada deve incluir:
- evidência de origem;
- identificador interno;
- tipo;
- resumo;
- relevância;
- utilização sugerida;
- lacunas;
- confiança;
- necessidade de revisão humana.

Requisitos:
- Cada item deve ser rastreável até uma evidência original.
- Persistir resultados com tenant_id e auditoria completa.
- Não emitir conclusão jurídica definitiva.
- Criar testes com mocks de LLM e dados sintéticos.
- Atualizar o grafo para encaminhar a saída ao módulo research somente após a etapa de evidências estar concluída ou explicitamente revisada por humano.
```

**Verificar depois**

- [ ] Todo achado tem vínculo com arquivo, página, trecho ou URL de origem.
- [ ] O sistema distingue claramente fato, inferência e ausência de informação.
- [ ] A saída aponta documentos faltantes: BO, comprovante PIX, URL de perfil, protocolo de denúncia.
- [ ] Não existem provas ou transcrições “criadas” pelo modelo.

### 3.4 — Central de evidências e inventário

`Aba Evidências` · trilha: **Interface**

**Objetivo:** Transformar o caso em uma pasta probatória organizada — upload com status real de processamento, inventário e painel de pendências documentais.

**Telas desta etapa**

| Tela | Usuário faz | Resultado |
|---|---|---|
| Central de Evidências | Envia e organiza arquivos | Arquivos vinculados ao caso |
| Inventário Probatório | Vê o que foi identificado | Fatos, lacunas e relevância |
| Pendências Documentais | Marca o que falta | Direciona a coleta de provas |

**Prompt para o Claude Code**

```text
Implemente a fatia frontend da Fase 3 — Evidências.

Antes de editar:
1. Leia CLAUDE.md.
2. Inspecione os endpoints e schemas reais de upload, evidência, processamento, inventário e permissões.
3. Reutilize o padrão de componentes e layout existente.
4. Não presuma URLs públicas de arquivos ou acesso direto a storage.

Na página de detalhe do caso, implemente a aba ou seção "Evidências" com:

1. Área de upload:
   - seleção de um ou mais arquivos apenas se a API suportar;
   - validações visuais coerentes com as validações reais do backend;
   - exibição de progresso quando suportado;
   - mensagens claras para arquivo inválido, tamanho excedido ou falha;
   - indicação de que arquivos originais serão preservados;
   - sem expor links públicos permanentes para documentos.

2. Lista/inventário:
   - nome original;
   - tipo;
   - data de recebimento;
   - status de processamento;
   - origem;
   - indicador de duplicidade, quando retornado pela API;
   - ações autorizadas: visualizar, baixar se permitido, solicitar reprocessamento se existir endpoint.

3. Painel de pendências:
   - documentos recebidos;
   - documentos faltantes;
   - documentos dispensados;
   - origem da pendência: triagem, evidência ou revisão humana.

4. Navegação para detalhe de uma evidência.

Estados obrigatórios:
- upload em curso;
- processamento;
- processado;
- falhou;
- sem evidências;
- erro de permissão.

Regras:
- O frontend não calcula ou declara integridade do arquivo; exibe os dados fornecidos pelo backend.
- Não afirmar que OCR/transcrição é perfeita.
- Não permitir que a interface altere ou sobrescreva arquivo original.
- Não permitir acesso a evidência se a API negar autorização.
- Criar testes de upload, falha, status de processamento, inventário vazio e acesso negado.

Execute os testes.
```

**Verificar depois**

- [ ] O advogado vê quais documentos chegaram e quais estão faltando.
- [ ] O upload apresenta status, e não apenas “sucesso” imediato.
- [ ] Um arquivo em OCR aparece como “processando”.
- [ ] Arquivos não ficam expostos por URL pública na interface.

### 3.5 — Visualizador de evidência e validação de OCR

`Detalhe de evidência` · trilha: **Interface**

**Objetivo:** Permitir comparar o original com o texto extraído, deixando explícito que OCR e transcrição são conteúdo derivado — e registrar a correção humana sem sobrescrever nada.

**Telas desta etapa**

| Tela | Usuário faz | Resultado |
|---|---|---|
| Visualizador de Evidência | Compara original e extração | Valida OCR/transcrição |
| Achados do inventário | Confere fatos, URLs, datas e valores | Cada achado aponta para a origem |
| Revisão humana | Confirma ou aponta erro de extração | Correção auditada, original intacto |

**Prompt para o Claude Code**

```text
Implemente a tela de detalhe de evidência e validação humana de OCR/transcrição.

Antes de editar:
- Inspecione os dados realmente retornados pelo backend para arquivo original, texto extraído, confiança, achados, páginas, trechos e processamento.
- Não invente coordenadas de OCR, páginas ou visualização de PDF se a API ainda não fornecer esses dados.

A tela deve incluir:

1. Metadados:
   - tipo de evidência;
   - data de upload;
   - status;
   - origem;
   - cadeia de custódia simplificada disponível;
   - hash ou identificador técnico apenas se a política de produto permitir sua exibição.

2. Visualização protegida do original:
   - usar o mecanismo de acesso autenticado existente;
   - evitar URL pública permanente;
   - tratar arquivos não visualizáveis.

3. Conteúdo extraído:
   - texto do OCR/PDF;
   - transcrição, quando disponível;
   - indicação clara de confiança/limitações;
   - separação visual entre conteúdo original e conteúdo derivado.

4. Resultado do inventário:
   - fatos identificados;
   - URLs, datas, valores ou identificadores extraídos;
   - relevância sugerida;
   - lacunas;
   - referência à origem da evidência.

5. Revisão humana:
   - confirmar conteúdo;
   - apontar erro de extração;
   - registrar observação;
   - devolver para reprocessamento apenas se houver suporte no backend.

Regras:
- Não permitir edição silenciosa do texto extraído.
- Uma correção humana deve criar registro/auditoria, não substituir o original.
- Mostrar aviso de que o conteúdo extraído requer conferência.
- Criar testes para visualização, ausência de extração, falha de processamento e envio de correção humana.

Execute os testes.
```

**Verificar depois**

- [ ] O advogado consegue comparar o original com o texto extraído.
- [ ] A interface mostra que OCR é conteúdo derivado.
- [ ] Correções humanas ficam registradas.
- [ ] O sistema não trata texto extraído como prova perfeita.

---

## Fase 4 — Pesquisa jurídica verificável

*Módulo LangGraph: research*

**Objetivo da fase:** Criar fontes jurídicas estruturadas e rastreáveis. A pesquisa deve ser assistida, nunca alucinada.

### 4.1 — Implementar LegalSource

`Modelo · persistência · ciclo de vida` · trilha: **Backend · orquestração**

**Objetivo:** Uma única estrutura para toda fonte jurídica, com origem verificável, status de verificação e trilha de aprovação humana.

**Prompt para o Claude Code**

```text
Implemente o modelo e a camada de persistência LegalSource para a Fase 4 — Pesquisa Jurídica.

Antes de editar:
- Inspecione modelos, migrations, padrões de tenant_id, RLS, audit_log e schemas existentes.
- Não invente entidades se já houver modelo equivalente.

O LegalSource deve suportar, no mínimo:
- tenant_id;
- case_id opcional;
- tipo de fonte: legislação, jurisprudência, doutrina, regulamento, política de plataforma;
- título;
- órgão/tribunal/editora/origem;
- identificador oficial ou número processual, quando houver;
- URL ou referência oficial verificável;
- data de publicação/julgamento, quando houver;
- trecho utilizado;
- metadados estruturados;
- hash do conteúdo ou da resposta de origem, quando aplicável;
- data de coleta;
- status de verificação;
- grau de aderência ao caso;
- vínculo com o agente/módulo que a utilizou.

Regras:
- Fonte sem origem verificável deve receber status não verificado e não pode ser promovida automaticamente a citação utilizável.
- Nenhuma fonte pode cruzar tenants sem regra explícita e auditada.
- Toda criação, edição e aprovação humana deve ser auditada.
- Criar migrations, schemas, repositórios/serviços e testes de tenancy/RLS.
- Documentar o ciclo de vida de uma fonte: coletada, validada, aprovada, rejeitada.
```

**Verificar depois**

- [ ] Existe uma única estrutura para fontes legais.
- [ ] Jurisprudência sem dados mínimos não é aceita como validada.
- [ ] Uma fonte aprovada por humano registra quem aprovou e quando.
- [ ] Cada citação futura poderá apontar para um LegalSource.

### 4.2 — Pesquisa de legislação e jurisprudência

`Nós legislation e jurisprudence` · trilha: **Backend · orquestração**

**Objetivo:** Propor dispositivos legais e decisões com referência oficial, tratando integrações externas como opcionais e falhas como falhas — nunca como invenção.

**Prompt para o Claude Code**

```text
Implemente os nós de pesquisa legislativa e jurisprudencial para o Squad Digital.

Antes de editar:
- Leia os prompts legislation.md e jurisprudence.md.
- Inspecione integrações existentes e variáveis de ambiente.
- Nunca inclua chaves de API em código, documentação ou logs.
- Não assuma que um endpoint externo está disponível: trate integração como opcional e falha controlada.

Implemente:
1. Nó legislation:
   - recebe fatos e modalidade do caso;
   - propõe dispositivos legais relevantes;
   - exige referência oficial e trecho verificável;
   - persiste cada fonte como LegalSource;
   - marca itens sem confirmação como pendentes de validação humana.

2. Nó jurisprudence:
   - pesquisa por parâmetros configuráveis;
   - normaliza resultados;
   - persiste processo, tribunal, ementa, datas, relator, link/origem e trechos disponíveis;
   - classifica aderência ao caso;
   - nunca fabrica número processual, ementa, relator ou data.

Requisitos de segurança e qualidade:
- Usar adaptadores de integração desacoplados.
- Aplicar timeouts, retries limitados e tratamento de rate limit.
- Registrar no audit_log parâmetros de pesquisa, sem registrar segredos.
- Fornecer modo mock para testes.
- Exigir revisão humana antes de uma jurisprudência ser usada em minuta.
- Criar testes de sucesso, fonte incompleta, fonte não verificável, timeout e isolamento por tenant.
```

**Verificar depois**

- [ ] Cada decisão tem tribunal, identificador/origem e status de verificação.
- [ ] Em falha da integração, o sistema informa “pesquisa indisponível” em vez de inventar resultado.
- [ ] A minuta futura não pode usar jurisprudência marcada como não verificada.
- [ ] Chaves de APIs externas estão exclusivamente em variáveis de ambiente.

### 4.3 — Doutrina e aprovação humana de fontes

`Nó doctrine · fluxo de validação` · trilha: **Backend · orquestração**

**Objetivo:** Aceitar citação direta apenas com trecho, edição e página verificáveis; e dar ao advogado o poder de aprovar, rejeitar ou corrigir cada fonte.

**Prompt para o Claude Code**

```text
Implemente o nó de doutrina e o fluxo de validação humana de fontes jurídicas.

Leia o prompt prompts/digital/research/doctrine.md e a implementação atual de LegalSource.

O nó deve:
- receber os temas jurídicos do caso;
- organizar referências doutrinárias candidatas;
- exigir dados bibliográficos suficientes;
- aceitar citação direta somente quando houver trecho, edição e página verificáveis;
- registrar paráfrases explicitamente como paráfrases;
- impedir que conteúdo não verificável seja apresentado como citação literal.

Implemente também:
- endpoint ou mecanismo interno para advogado humano aprovar, rejeitar ou corrigir uma fonte;
- justificativa de aprovação/rejeição;
- auditoria de todas as decisões;
- regra que bloqueia o uso em estratégia/minuta de fontes não aprovadas, salvo se a arquitetura já definir uma permissão explícita de "uso como rascunho não verificado".

Crie testes para:
- citação verificável;
- citação sem página;
- paráfrase;
- aprovação humana;
- tentativa de usar fonte não verificada em módulo posterior.
```

**Verificar depois**

- [ ] Não há citação doutrinária falsa ou sem página apresentada como literal.
- [ ] Uma fonte rejeitada não pode reaparecer na estratégia como válida.
- [ ] A aprovação do advogado é rastreável.

### 4.4 — Biblioteca jurídica e aprovação de fontes

`Aba Pesquisa · fila de validação` · trilha: **Interface**

**Objetivo:** Tornar visível na tela a diferença entre fonte encontrada, verificável, aprovada, rejeitada e pendente — e dar ao advogado o botão que faz essa distinção valer.

**Telas desta etapa**

| Tela | Usuário faz | Resultado |
|---|---|---|
| Pesquisa do Caso | Consulta pesquisas realizadas | Visualiza parâmetros e resultados |
| Biblioteca de Fontes | Filtra legislação, jurisprudência e doutrina | Organiza os LegalSource |
| Detalhe da Fonte | Confere origem e trecho | Aprova, rejeita ou corrige |
| Fila de Validação | Vê fontes pendentes | Controla a revisão humana |

**Prompt para o Claude Code**

```text
Implemente a fatia frontend da Fase 4 — Pesquisa jurídica verificável.

Antes de editar:
1. Inspecione os endpoints e schemas reais de LegalSource, pesquisa, status de verificação, aprovação e rejeição.
2. Não invente campos bibliográficos, URLs, identificadores processuais ou estados inexistentes.
3. Use os componentes de status, confirmação e revisão humana já criados.

Implemente:

1. Aba "Pesquisa" dentro do detalhe do caso:
   - resumo das pesquisas já executadas;
   - status de cada execução;
   - filtros por tipo de fonte, quando suportado;
   - ação para iniciar pesquisa somente se a API fornecer esse recurso;
   - indicação de falha de integração sem substituir o erro por resultado fictício.

2. Lista de fontes:
   - tipo: legislação, jurisprudência, doutrina, regulamento ou política de plataforma;
   - título;
   - órgão/origem;
   - data, quando disponível;
   - status: coletada, verificada, aprovada, rejeitada ou pendente;
   - grau de aderência, se devolvido pela API;
   - indicação de fonte oficial/verificável;
   - acesso ao detalhe.

3. Tela ou painel de detalhe de fonte:
   - metadados completos disponíveis;
   - trecho utilizado;
   - link de origem quando fornecido pela API;
   - data de coleta;
   - justificativa de aderência;
   - alertas de ausência de verificação.

4. Ações humanas:
   - aprovar;
   - rejeitar;
   - solicitar correção;
   - inserir justificativa obrigatória em rejeição/correção;
   - exibir histórico de decisões.

Regras:
- Nunca apresentar fonte pendente ou não verificada como citação válida.
- Não gerar número processual, ementa, página de livro ou URL artificialmente.
- Não permitir aprovação apenas visual: ação deve passar pelo backend e ser auditada.
- Criar testes de listagem, filtro, aprovação, rejeição, fonte incompleta e falha de API.

Execute os testes.
```

**Verificar depois**

- [ ] A fonte tem status claro, sem ambiguidade.
- [ ] Jurisprudência sem dados suficientes não aparece como “aprovada”.
- [ ] O advogado vê a origem e o trecho antes de aprovar.
- [ ] Fontes rejeitadas permanecem no histórico, mas não são elegíveis para a estratégia.

---

## Fase 5 — Estratégia jurídica assistida

*Módulo LangGraph: strategy*

**Objetivo da fase:** Consolidar evidências e fontes aprovadas em uma recomendação estratégica que depende de validação humana para avançar.

### 5.1 — Nó strategist

`orchestrator/graphs/strategy.py` · trilha: **Backend · orquestração**

**Objetivo:** Produzir tese, foro sugerido, avaliação de tutela, pedidos, riscos e lacunas — sempre como hipótese vinculada a fontes aprovadas.

**Prompt para o Claude Code**

```text
Implemente o módulo strategy do Squad Digital usando LangGraph.

Antes de editar:
- Leia o CaseState e o prompt prompts/digital/strategy/strategist.md.
- Inspecione os outputs reais dos módulos intake, evidence e research.
- Não adicione campos ao estado sem justificar e documentar a alteração.

O nó strategist deve consumir apenas:
- dados de intake revisados ou marcados com confiança;
- evidências rastreáveis;
- LegalSources verificadas/aprovadas conforme as regras do projeto;
- informações explicitamente marcadas como pendentes.

Produza uma recomendação estruturada contendo:
- síntese de fatos e fatos pendentes;
- tese principal e teses subsidiárias;
- competência/foro sugerido como hipótese a confirmar;
- avaliação de tutela de urgência;
- pedidos sugeridos;
- riscos;
- argumentos adversos prováveis;
- documentos e confirmações necessários;
- fontes usadas, vinculadas pelos respectivos LegalSource IDs;
- aviso obrigatório de que a estratégia exige aprovação de advogado responsável.

Regras:
- Não afirmar probabilidade de êxito como fato objetivo.
- Se houver dados insuficientes, bloquear ou solicitar informação.
- Não tomar decisão processual final.
- Registrar input/output hashes, fontes utilizadas, prompt version e usuário/serviço ator no audit_log.
- Criar testes para caso completo, caso sem fontes verificadas, caso sem evidências e caso com dados contraditórios.
```

**Verificar depois**

- [ ] A estratégia não usa evidência sem origem.
- [ ] As fontes ficam listadas e consultáveis internamente.
- [ ] O sistema aponta riscos e lacunas, em vez de esconder incerteza.
- [ ] A aprovação humana é obrigatória antes da produção da peça.

### 5.2 — Aprovação, correção e versionamento

`Máquina de estados · RBAC` · trilha: **Backend · orquestração**

**Objetivo:** Dar ao advogado o controle de aprovar, rejeitar, editar ou devolver a etapas anteriores — com histórico imutável de versões.

**Prompt para o Claude Code**

```text
Implemente o fluxo de revisão humana para a estratégia jurídica.

A solução deve permitir que um usuário com papel jurídico adequado:
- visualize a estratégia;
- aprove;
- rejeite;
- edite pontos específicos;
- solicite retorno a intake, evidence ou research;
- registre justificativa e comentários;
- gere nova versão mantendo o histórico imutável das versões anteriores.

Requisitos:
- Toda versão deve ter identificador, timestamp, autor, input_hash, output_hash e status.
- Não sobrescrever a estratégia anterior.
- Não permitir transição à produção da peça enquanto não houver estratégia aprovada.
- Aplicar tenant_id, RBAC, RLS e audit_log.
- Criar testes de transições permitidas e bloqueadas, permissões e isolamento entre tenants.
- Atualizar a máquina de estados/documentação do fluxo.
```

**Verificar depois**

- [ ] A estratégia aprovada não é editada silenciosamente.
- [ ] O histórico mostra quem alterou o quê e por quê.
- [ ] Apenas papel autorizado aprova uma estratégia.
- [ ] O grafo bloqueia a ida para drafting sem aprovação.

### 5.3 — Painel de estratégia e aprovação

`Aba Estratégia` · trilha: **Interface**

**Objetivo:** A tela precisa deixar explícito que a estratégia é recomendação estruturada, não decisão automática: riscos à vista, cada fundamento clicável até a fonte, e o estado bloqueado explicando o que falta.

**Anatomia da tela**

```text
Estratégia do Caso
├── Fatos confirmados
├── Pontos pendentes
├── Tese principal
├── Teses subsidiárias
├── Competência sugerida
├── Tutela de urgência
├── Pedidos sugeridos
├── Riscos e argumentos contrários
├── Evidências utilizadas
├── Fontes jurídicas utilizadas
├── Histórico de versões
└── Ações humanas
    ├── Aprovar
    ├── Corrigir
    ├── Devolver para evidências
    └── Devolver para pesquisa
```

**Prompt para o Claude Code**

```text
Implemente a fatia frontend da Fase 5 — Estratégia jurídica assistida.

Antes de editar:
- Inspecione os endpoints, schemas e estados reais de estratégia, versão, aprovação, devolução e permissões.
- Confirme quais módulos anteriores precisam estar aprovados para liberar a estratégia.
- Não invente campos ou transições de estado.

Implemente na página de detalhe do caso uma aba ou seção "Estratégia" com:

1. Estado bloqueado:
   - explicar quais pré-requisitos ainda faltam;
   - links para Intake, Evidências ou Pesquisa, quando aplicável;
   - não permitir gerar estratégia enquanto o backend negar a ação.

2. Estratégia gerada:
   - fatos confirmados;
   - fatos pendentes;
   - tese principal;
   - teses subsidiárias;
   - competência/foro sugeridos como hipótese;
   - tutela de urgência;
   - pedidos sugeridos;
   - riscos;
   - argumentos adversos prováveis;
   - documentos ou confirmações necessários.

3. Rastreabilidade:
   - cada evidência utilizada deve apontar para a evidência interna correspondente;
   - cada fundamento deve apontar para a LegalSource correspondente;
   - fontes pendentes, rejeitadas ou não verificadas devem aparecer como bloqueantes, se retornadas pela API.

4. Revisão humana:
   - Aprovar estratégia;
   - Solicitar correção;
   - Devolver a evidências;
   - Devolver à pesquisa;
   - exigir justificativa para devolução ou correção;
   - apresentar versão, autor e data de cada decisão.

5. Segurança visual:
   - aviso permanente: "Estratégia assistida. Exige validação do advogado responsável."
   - não usar linguagem que indique decisão processual final ou êxito garantido.

Crie testes de:
- estratégia bloqueada;
- estratégia disponível;
- links de rastreabilidade;
- aprovação;
- correção;
- devolução;
- erro de API e permissão insuficiente.

Execute os testes.
```

**Verificar depois**

- [ ] O advogado enxerga riscos, não apenas a tese favorável.
- [ ] Cada fundamento tem uma fonte associada.
- [ ] A estratégia não segue para minuta sem aprovação humana.
- [ ] A devolução para Pesquisa ou Evidências é registrada e muda o fluxo corretamente.

---

## Fase 6 — Produção da peça jurídica

*Módulo LangGraph: drafting*

**Objetivo da fase:** Gerar uma minuta editável, com blocos rastreáveis — jamais uma peça pronta para protocolo autônomo.

### 6.1 — Nó skeleton

`Estrutura da peça` · trilha: **Backend · orquestração**

**Objetivo:** Produzir a estrutura da peça com objetivo de cada bloco, vínculo a evidências e fontes, e marcação explícita do que está pendente.

**Prompt para o Claude Code**

```text
Implemente o nó skeleton no módulo drafting.

Leia:
- prompts/digital/drafting/skeleton.md;
- estratégia aprovada;
- evidências rastreáveis;
- LegalSources aprovadas;
- convenções de versionamento e auditoria existentes.

O nó deve produzir uma estrutura de peça, não uma petição final, contendo:
- seções e subseções;
- objetivo de cada bloco;
- fatos que podem ser afirmados, com links/referências às evidências;
- fundamentos, com vínculo aos LegalSource IDs;
- pedidos sugeridos;
- campos faltantes marcados explicitamente como [PENDENTE DE CONFIRMAÇÃO HUMANA];
- pontos que exigem qualificação, valores, foro ou assinatura do advogado.

Regras:
- Não incluir citação sem LegalSource aprovado.
- Não preencher nome, CPF, endereço, CNPJ, OAB, comarca ou valores quando não existirem nos dados do caso.
- Não produzir instruções de protocolo.
- Registrar versão, hashes e fontes em auditoria.
- Criar testes que garantam que dados ausentes sejam marcados como pendentes, nunca inventados.
```

**Verificar depois**

- [ ] O esqueleto não contém dados pessoais fictícios.
- [ ] Cada bloco jurídico tem fonte ou indicação de pendência.
- [ ] Os documentos e fontes aparecem vinculados a cada seção.

### 6.2 — Nó writer (redação Visual Law)

`Minuta para revisão humana` · trilha: **Backend · orquestração**

**Objetivo:** Redigir a minuta preservando a estrutura aprovada, com rastreabilidade de cada alegação e status permanente de rascunho.

**Prompt para o Claude Code**

```text
Implemente o nó writer para redigir uma minuta jurídica editável a partir de um esqueleto aprovado.

Leia:
- prompts/digital/drafting/writer.md;
- o esqueleto aprovado;
- as fontes aprovadas;
- a política de revisão humana;
- as regras de formatação do projeto.

A redação deve:
- preservar a estrutura do esqueleto;
- aplicar o padrão Visual Law definido no projeto;
- manter referências rastreáveis a evidências e LegalSources;
- diferenciar citações diretas, paráfrases e alegações baseadas em prova;
- manter campos pendentes claramente destacados;
- gerar uma minuta em formato estruturado compatível com o armazenamento já adotado pelo projeto;
- nunca sinalizar "pronta para protocolo"; o status deve ser "minuta para revisão humana".

Requisitos:
- Não inventar fatos, fontes, números processuais, valores ou citações.
- Não usar fonte não aprovada.
- Manter metadados de versão, prompt, hashes e fontes.
- Criar testes com mocks que validem rastreabilidade, presença de placeholders e bloqueio de fonte não aprovada.
```

**Verificar depois**

- [ ] A minuta mostra PENDENTE DE CONFIRMAÇÃO HUMANA onde faltar informação.
- [ ] Citações apontam para a fonte armazenada.
- [ ] Não há dado jurídico inventado.
- [ ] O status é de minuta, não de peça protocolável.

### 6.3 — Esqueleto e editor de minuta

`Aba Minuta · versionamento` · trilha: **Interface**

**Objetivo:** Aqui o frontend pesa mais que em qualquer outra fase. Não comece por um editor jurídico complexo: entregue edição estruturada, seções claras, pendências destacadas, rastreabilidade e versões salvas.

**Telas desta etapa**

| Tela | Usuário faz | Resultado |
|---|---|---|
| Esqueleto | Revisa a estrutura antes da redação | Controla a organização da peça |
| Minuta | Lê e edita o conteúdo | Produz versão revisável |
| Painel de rastreabilidade | Consulta fontes e provas usadas | Confere cada alegação |
| Histórico de versões | Compara alterações | Mantém integridade e auditoria |

**Prompt para o Claude Code**

```text
Implemente a fatia frontend da Fase 6 — Produção da peça.

Antes de editar:
1. Inspecione os endpoints e schemas reais de skeleton, draft, versões, seções, citações, placeholders, aprovação e auditoria.
2. Identifique se o projeto já adota Markdown, rich text, HTML estruturado ou outro formato para minuta.
3. Não introduza um editor incompatível com o formato de persistência existente.
4. Não invente campos de petição, dados processuais, partes, comarca, OAB ou valores.

Implemente uma aba ou seção "Minuta" com duas etapas:

1. Esqueleto:
   - exibir seções e subseções;
   - objetivo de cada bloco;
   - fatos/evidências utilizados;
   - fontes jurídicas vinculadas;
   - placeholders pendentes;
   - ação humana para aprovar ou solicitar correção do esqueleto, quando suportada pelo backend.

2. Minuta editável:
   - editor compatível com o formato real do projeto;
   - áreas/seções claramente organizadas;
   - destaque visual para [PENDENTE DE CONFIRMAÇÃO HUMANA];
   - referências rastreáveis para evidências e LegalSources;
   - painel lateral ou equivalente para consultar fontes e provas sem perder o contexto;
   - salvamento explícito;
   - tratamento de conflito de versão, se a API fornecer versionamento;
   - histórico de versões e autoria;
   - status permanente: "Minuta para revisão humana — não pronta para protocolo".

3. Ações:
   - salvar rascunho;
   - solicitar nova geração apenas se existir endpoint;
   - enviar para revisão;
   - retornar à estratégia, quando necessário.

Regras:
- Não remover automaticamente placeholders pendentes.
- Não permitir enviar para revisão se a API indicar bloqueios.
- Não ocultar fontes não verificadas ou pendências.
- Não oferecer botão de protocolo, peticionamento ou envio a tribunal.
- Toda alteração humana relevante precisa ser persistida e auditada pelo backend.

Crie testes para:
- visualização de esqueleto;
- edição e salvamento;
- placeholders;
- rastreabilidade de fonte e evidência;
- bloqueio por pendência;
- histórico de versões;
- falha de salvamento.

Execute os testes.
```

**Verificar depois**

- [ ] Campos pendentes permanecem visíveis no editor.
- [ ] O usuário consegue abrir a fonte/evidência relacionada a um trecho.
- [ ] Versões anteriores são preservadas.
- [ ] Não existe botão ou linguagem de “protocolar peça”.

---

## Fase 7 — Qualidade e aprendizado controlado

*Módulo LangGraph: review*

**Objetivo da fase:** Revisar de forma assistida, registrar correções humanas e transformar feedback em insumos versionados — sem autoalterar prompts em produção.

### 7.1 — Nó reviewer e checklist verificável

`Aprovado · ressalva · erro · bloqueante` · trilha: **Backend · orquestração**

**Objetivo:** Checar coerência entre minuta, provas e fontes, emitindo lista objetiva de correções sem alterar a minuta silenciosamente.

**Prompt para o Claude Code**

```text
Implemente o módulo review do Squad Digital, começando pelo nó reviewer.

Leia:
- prompts/digital/review/reviewer.md;
- a minuta produzida;
- a estratégia aprovada;
- LegalSources;
- inventário de evidências;
- regras de RBAC e auditoria.

O reviewer deve executar verificações estruturadas, incluindo:
- coerência entre fatos da minuta e evidências;
- presença de campos pendentes;
- existência e status das fontes citadas;
- consistência de pedidos e valor da causa, quando dados suficientes existirem;
- identificação de possível competência/foro pendente;
- referência a tutela de urgência apenas quando prevista na estratégia aprovada;
- integridade dos metadados e versões.

Classifique cada item como: aprovado, ressalva, erro ou bloqueante.

Regras:
- O revisor não pode "corrigir silenciosamente" a minuta.
- Deve emitir lista objetiva de correções.
- Citação sem fonte verificável é bloqueante.
- Dados incompletos devem gerar pendência, não preenchimento automático.
- A decisão final de aprovação é sempre humana.

Crie testes para inconsistência de provas, citação inválida, campo pendente, pedido incompatível e fluxo de bloqueio.
```

**Verificar depois**

- [ ] O revisor bloqueia citações não verificadas.
- [ ] Nenhum erro é corrigido sem registro.
- [ ] A minuta segue para humano mesmo quando o checklist automático estiver aprovado.
- [ ] O resultado indica exatamente qual seção exige correção.

### 7.2 — Aprendizado por feedback, sem autoedição

`Sugestões versionadas` · trilha: **Backend · orquestração**

**Objetivo:** Coletar feedback humano, medir qualidade por módulo e propor mudanças de prompt como sugestão — nunca aplicá-las sozinho.

**Prompt para o Claude Code**

```text
Implemente o componente learning da Fase 7 como sistema de coleta e análise de feedback, sem alteração automática de prompts ou regras em produção.

Leia prompts/digital/review/learning.md e a arquitetura de auditoria.

Implemente:
- registro de feedback humano sobre intake, evidências, pesquisa, estratégia, esqueleto, minuta e revisão;
- categorização de erros recorrentes;
- métricas de qualidade por módulo, tenant e período;
- relatório de padrões de melhoria;
- sugestão de mudanças em prompts, templates ou checklists como proposta versionada;
- fluxo obrigatório de aprovação humana antes de qualquer mudança ser aplicada aos prompts.

Restrições:
- Não treinar modelo automaticamente com dados de clientes.
- Não mover dados entre tenants.
- Não alterar arquivo de prompt em produção de modo autônomo.
- Não usar dados pessoais desnecessários em relatórios agregados.
- Registrar toda sugestão e aprovação no audit_log.

Crie testes de isolamento entre tenants, criação de sugestão, bloqueio de autoaplicação e trilha de auditoria.
```

**Verificar depois**

- [ ] O módulo gera sugestões, não mudanças automáticas.
- [ ] Uma alteração de prompt exige PR/commit e aprovação humana.
- [ ] Métricas de um escritório não aparecem para outro.
- [ ] Feedback do revisor é rastreável até a versão da minuta analisada.

### 7.3 — Central de revisão e feedback

`Aba Revisão · checklist` · trilha: **Interface**

**Objetivo:** A revisão precisa ter experiência de checklist. O advogado não deve caçar problemas em telas diferentes: do achado bloqueante ao trecho afetado em um clique.

**Anatomia da tela**

```text
Revisão da Minuta
├── Resumo de status
├── Itens aprovados
├── Ressalvas
├── Erros
├── Bloqueantes
├── Trecho afetado
├── Evidência/fonte relacionada
├── Ação recomendada
├── Comentário do advogado
└── Decisão final humana
```

**Prompt para o Claude Code**

```text
Implemente a fatia frontend da Fase 7 — Revisão, qualidade e feedback humano.

Antes de editar:
- Inspecione endpoints, schemas e estados reais do módulo reviewer, checklist, correções, bloqueios, feedback e aprovação final.
- Não trate uma revisão automática como aprovação jurídica definitiva.

Implemente na página de detalhe do caso a aba ou seção "Revisão" com:

1. Resumo:
   - status geral;
   - quantidade de itens aprovados;
   - quantidade de ressalvas;
   - quantidade de erros;
   - quantidade de bloqueantes;
   - indicação clara de que a aprovação final é humana.

2. Lista de achados:
   - classificação: aprovado, ressalva, erro ou bloqueante;
   - regra/checklist que gerou o achado;
   - seção ou trecho afetado;
   - evidência ou LegalSource relacionada, quando disponível;
   - sugestão de correção;
   - status de resolução.

3. Fluxo de trabalho:
   - navegar do achado para a seção correspondente da minuta;
   - marcar como resolvido, quando permitido;
   - registrar comentário humano;
   - devolver para redação, estratégia, evidências ou pesquisa;
   - registrar decisão final humana conforme os estados suportados pelo backend.

4. Feedback:
   - formulário de feedback sobre a qualidade da triagem, evidências, pesquisa, estratégia, minuta e revisão;
   - categorias de erro existentes no backend;
   - observação textual;
   - sem permitir que o frontend altere prompts ou regras diretamente.

Regras:
- Achado bloqueante deve ser visualmente destacado.
- Não permitir marcação de resolvido sem chamada válida ao backend.
- Não esconder achados pendentes.
- Não oferecer "aprovação automática".
- Toda decisão humana deve aparecer no histórico do caso.

Crie testes para:
- exibição de checklist;
- filtro por severidade;
- navegação para trecho da minuta;
- comentário humano;
- devolução de etapa;
- bloqueante impedindo aprovação;
- feedback enviado com sucesso e falha de API.

Execute os testes.
```

**Verificar depois**

- [ ] Bloqueantes são impossíveis de ignorar visualmente.
- [ ] O advogado pode ir do problema direto ao trecho afetado.
- [ ] A revisão não altera a minuta de modo silencioso.
- [ ] Feedback fica registrado, mas não altera prompts automaticamente.

---

## Fase 8 — End-to-end, segurança e piloto interno

*Fechamento do MVP*

**Objetivo da fase:** Fechar o MVP com testes integrados, observabilidade e operação segura para uso interno supervisionado.

### 8.1 — Teste completo do fluxo com caso sintético

`CI · dois tenants` · trilha: **Backend · orquestração**

**Objetivo:** Percorrer as 13 etapas do fluxo com dados sintéticos, validando isolamento e ordem autorizada de transições.

**Prompt para o Claude Code**

```text
Crie testes end-to-end para o fluxo completo do MVP do Squad Digital usando exclusivamente dados sintéticos.

O cenário deve percorrer:
1. criação do caso;
2. intake e triagem;
3. upload de evidências;
4. extração de texto/OCR com mock;
5. inventário probatório;
6. pesquisa jurídica com fontes mockadas e verificáveis;
7. aprovação humana das fontes;
8. estratégia;
9. aprovação humana da estratégia;
10. esqueleto;
11. minuta;
12. revisão;
13. coleta de feedback.

Requisitos:
- Usar pelo menos dois tenants distintos para validar isolamento em cada etapa.
- Mockar LLMs e integrações externas.
- Validar que cada ação relevante gera audit_log.
- Validar que não há transição para drafting sem estratégia aprovada.
- Validar que não há uso de fonte não verificada.
- Validar que a minuta final é marcada como revisão humana obrigatória.

Não use dados reais de clientes.
Produza documentação de como executar o teste localmente e no CI.
```

**Verificar depois**

- [ ] O fluxo completo passa no CI.
- [ ] O caso de um tenant não aparece em nenhuma resposta, log ou consulta do outro.
- [ ] Não há avanço de estado fora da sequência autorizada.
- [ ] O relatório final traz evidências e fontes rastreáveis.

### 8.2 — Segurança, observabilidade e prontidão de piloto

`docs/mvp_pilot_readiness.md` · trilha: **Backend · orquestração**

**Objetivo:** Health checks, logs sem dado sensível, validação de env na inicialização, backup, rollback e checklist operacional do piloto.

**Prompt para o Claude Code**

```text
Faça uma revisão final de prontidão para piloto interno do MVP Squad Digital.

Leia CLAUDE.md, docs/architecture.md, docs/phase_1_audit.md e toda a documentação das fases implementadas.

Implemente ou complete:
- health checks;
- logs estruturados sem conteúdo sensível desnecessário;
- correlação de requisições/casos sem expor dados pessoais;
- monitoramento de erros de integrações e workers;
- política de retenção de arquivos e dados conforme configuração do sistema;
- validação de variáveis de ambiente na inicialização;
- documentação de backup e restauração;
- documentação de execução local, testes e deploy;
- checklist operacional de piloto interno;
- checklist de revisão humana obrigatória antes de qualquer entrega jurídica.

Execute linters, testes, verificações de tipo e testes de integração disponíveis.

Gere docs/mvp_pilot_readiness.md com:
- itens aprovados;
- riscos remanescentes;
- itens bloqueantes;
- procedimento de rollback;
- roteiro de piloto com casos sintéticos primeiro.
```

**Verificar depois**

- [ ] Nenhuma chave aparece em código, logs ou documentação.
- [ ] O ambiente falha cedo se faltar variável crítica.
- [ ] Há procedimento de rollback documentado.
- [ ] O piloto começa apenas com casos selecionados e revisão humana obrigatória.
- [ ] A aplicação nunca se apresenta como sistema autônomo de protocolo ou aconselhamento jurídico final.

> Roteiro de piloto: casos sintéticos primeiro, depois 3–5 casos reais do Reis Esteves com revisão humana em cada etapa.

### 8.3 — Dashboard, fila de revisões e histórico

`Visão de operação do escritório` · trilha: **Interface**

**Objetivo:** Entregar a visão de operação real: casos em fila, revisões pendentes, gargalos e uma trilha de auditoria que o advogado entenda — sem vazar métricas entre tenants.

**Telas desta etapa**

| Tela | Usuário faz | Resultado |
|---|---|---|
| Dashboard | Vê casos por status e pendências | Sabe onde agir primeiro |
| Revisões Pendentes | Centraliza aprovações necessárias | Nada fica parado sem dono |
| Histórico do Caso | Lê a trilha auditável | Compreende decisões e versões |
| Configurações | Ajusta perfis e preferências | Apenas o que o RBAC permitir |
| Saúde do Sistema | Acompanha integrações e workers | Somente administradores |

**Prompt para o Claude Code**

```text
Implemente a fatia frontend final do MVP: Dashboard operacional, fila de revisões e histórico do caso.

Antes de editar:
1. Inspecione endpoints e permissões reais para dashboard, casos, revisões, auditoria e métricas.
2. Não invente métricas que não possam ser calculadas ou retornadas pelo backend.
3. Não exiba dados agregados de outros tenants.

Implemente:

1. Dashboard:
   - total de casos por etapa/status;
   - casos aguardando complementação;
   - casos aguardando revisão humana;
   - casos com bloqueantes;
   - atividade recente;
   - links para as ações correspondentes;
   - filtros disponíveis apenas se suportados pela API.

2. Fila de revisões pendentes:
   - tipo de revisão: triagem, fonte, estratégia, esqueleto, minuta ou checklist;
   - caso;
   - prioridade/urgência, se disponível;
   - responsável, se disponível;
   - data da última atualização;
   - ação para abrir o item correto no contexto do caso.

3. Histórico do caso:
   - linha do tempo compreensível ao advogado;
   - criação de caso;
   - uploads;
   - processamentos;
   - pesquisas;
   - aprovações, rejeições e devoluções;
   - versões de estratégia e minuta;
   - autor e data de cada ação;
   - não expor segredos, conteúdo técnico excessivo ou hashes internos sem necessidade.

4. Controle de acesso:
   - proteger informações administrativas por RBAC;
   - tratar resposta 403/401 corretamente;
   - não confiar exclusivamente em ocultar elementos da interface.

Crie testes para:
- dashboard com dados;
- dashboard vazio;
- fila de revisões;
- navegação para o caso;
- acesso negado;
- histórico cronológico;
- isolamento visual entre tenants conforme respostas da API.

Execute todos os testes disponíveis e atualize docs/mvp_pilot_readiness.md com os fluxos frontend entregues.
```

**Verificar depois**

- [ ] O advogado consegue identificar rapidamente o que exige revisão.
- [ ] O histórico mostra decisões humanas e versões relevantes.
- [ ] Não há métricas globais vazando dados entre tenants.
- [ ] A interface está pronta para testar um caso sintético de ponta a ponta.

---

## Definição de pronto por fase

Uma fase só pode ser marcada como concluída se cumprir todos estes pontos:

- [ ] API e regras de domínio implementadas.
- [ ] Fluxo LangGraph integrado quando aplicável.
- [ ] Tela correspondente disponível.
- [ ] Estados de carregamento, erro e vazio tratados.
- [ ] Ação humana de aprovação, correção ou devolução disponível quando necessária.
- [ ] Isolamento por tenant preservado.
- [ ] Auditoria registrada.
- [ ] Testes de backend e frontend aprovados.
- [ ] Sem linguagem ou recursos que impliquem protocolo judicial autônomo.

## Critério de “MVP concluído”

Tecnicamente pronto para piloto interno quando o sistema conseguir:

1. Criar um caso digital isolado por tenant.
2. Triar e classificar o caso com revisão humana.
3. Receber e organizar evidências preservando os originais.
4. Produzir pesquisa com fontes jurídicas verificáveis.
5. Gerar estratégia e minuta somente após aprovações humanas.
6. Rastrear cada alegação à prova ou fonte correspondente.
7. Revisar a minuta com checklist objetivo.
8. Registrar todas as etapas no audit_log.
9. Impedir acesso cruzado entre escritórios.
10. Operar como copiloto — nunca como mecanismo autônomo de protocolo.

---

**Regra de ouro:** não avance de fase sem o módulo anterior funcionando end-to-end com um caso de teste.
