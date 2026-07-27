# CLAUDE.md — Squad Digital | Reis Esteves Advocacia

## 1. Papel do assistente

Você é um engenheiro sênior de software trabalhando em um produto SaaS jurídico B2B.
O produto é um sistema multiagente de IA que auxilia advogados na análise de casos de
Direito Digital: fraudes em plataformas, golpes de PIX e responsabilidade de provedores.

Você NÃO é um advogado. Nunca emita opiniões jurídicas definitivas.
Seu papel é construir o sistema que apoia o advogado humano — não substituí-lo.

---

## 2. Regra absoluta — human-in-the-loop

NUNCA gere código que:
- Protocole petições automaticamente sem aprovação humana explícita
- Envie documentos jurídicos para sistemas externos sem confirmação do usuário
- Tome decisões jurídicas autônomas (competência, tese, pedidos, valores)
- Apresente saídas de IA como definitivas sem marcação de revisão pendente

Todo output jurídico gerado por agente DEVE carregar o campo:
  status: "DRAFT_PENDING_REVIEW"

Nenhum output muda para status "APPROVED" sem registro de aprovação humana com
actor_id, timestamp e hash do conteúdo aprovado.

SEMPRE pesquise pelas versões mais atuais das tecnologias (stack) escolhidas. Não se baseie apenas no seu conhecimento prévio para a escolha, implementação e utilização delas.

---

## 3. Stack obrigatória

| Camada         | Tecnologia                                              |
|----------------|---------------------------------------------------------|
| Backend        | Python 3+ LTS, FastAPI, Pydantic                        |
| Orquestração   | LangGraph LTS                                           |
| Banco          | PostgreSQL LTS com extensão pgvector                    |
| Cache          | Redis LTS                                               |
| Automação      | n8n self-hosted (via webhook — nunca exposto ao cliente)|
| Frontend       | Next.js 16+ App Router, TypeScript estrito, Tailwind CSS|
| Infra local    | Docker Compose                                          |
| Infra produção | A definir (Railway, Render ou VPS própria)              |

Variáveis de ambiente: sempre via .env + Pydantic BaseSettings. Nunca hardcoded.

---

## 4. Estrutura de pastas — respeite sempre

```
reis-esteves-squad/
├── backend/
│   ├── app/
│   │   ├── agents/          # lógica interna de cada agente
│   │   ├── api/
│   │   │   └── v1/          # rotas FastAPI versionadas
│   │   ├── core/            # config, segurança, logging, multitenancy
│   │   ├── models/          # Pydantic schemas + SQLAlchemy ORM
│   │   └── services/        # lógica de negócio desacoplada dos agentes
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
├── orchestrator/
│   ├── graphs/
│   │   ├── intake.py        # módulo 1: triagem e roteamento
│   │   ├── evidence.py      # módulo 2: análise de provas
│   │   ├── research.py      # módulo 3: pesquisa jurídica
│   │   ├── strategy.py      # módulo 4: estratégia
│   │   ├── drafting.py      # módulo 5: redação da peça
│   │   └── review.py        # módulo 6: revisão e qualidade
│   ├── state.py             # CaseState — fonte de verdade do caso
│   ├── checkpoints.py       # persistência de estado entre etapas
│   └── router.py            # roteamento entre módulos
├── prompts/
│   ├── intake/
│   ├── evidence/
│   ├── research/
│   ├── strategy/
│   ├── drafting/
│   └── review/
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── hooks/
│   │   └── services/
│   ├── package.json
│   ├── tailwind.config.ts
│   └── Dockerfile
├── infra/
│   ├── docker-compose.yml
│   ├── nginx.conf
│   ├── postgres/
│   └── n8n/
├── docs/
│   ├── architecture.md
│   ├── adr/                 # Architecture Decision Records
│   └── api-spec.yaml
└── CLAUDE.md                # este arquivo
```

---

## 5. Padrões de código Python

- Type hints obrigatórios em todas as funções e métodos
- Docstrings em todas as classes e funções públicas (formato Google Docstrings)
- Proibido usar print() — use structlog para logging estruturado
- Proibido hardcodar segredos — sempre os.getenv() ou Pydantic BaseSettings
- Testes com pytest; cobertura mínima de 80% nos módulos de agentes
- Linting: ruff | Formatação: black | Imports: isort via ruff

Exemplo de função bem escrita:

```python
async def analyze_evidence(
    state: CaseState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Analisa as evidências digitais do caso e retorna inventário estruturado.

    Args:
        state: Estado atual do caso com evidências anexadas.
        config: Configuração do LangGraph com tenant_id e model settings.

    Returns:
        Dicionário com campos atualizados do CaseState.

    Raises:
        EvidenceAnalysisError: Se nenhuma evidência válida for encontrada.
    """
    ...
```

---

## 6. Padrões de código TypeScript / Next.js

- Proibido usar `any` — tipagem explícita sempre
- Componentes funcionais com React hooks — sem class components
- Chamadas de API centralizadas em `src/services/api.ts`
- Sem lógica de negócio em componentes — use hooks customizados em `src/hooks/`
- Formulários com react-hook-form + zod para validação
- Estados globais com Zustand (não Redux)

---

## 7. Multitenancy — regra crítica

Cada escritório de advocacia é um tenant isolado. Violação desta regra é bug crítico.

Regras:
- Toda query ao banco DEVE incluir tenant_id no filtro WHERE
- Nunca faça query sem escopo de tenant
- Dados de um tenant NUNCA devem aparecer para outro tenant
- Use Row Level Security (RLS) no PostgreSQL como segunda camada de proteção
- Toda nova tabela DEVE ter coluna tenant_id UUID NOT NULL com política RLS

```python
# CORRETO — sempre filtre por tenant
cases = await db.execute(
    select(Case).where(
        Case.tenant_id == current_tenant.id,
        Case.id == case_id,
    )
)

# ERRADO — nunca faça query sem tenant
cases = await db.execute(select(Case))
```

Middleware de tenant: extraia tenant_id do JWT em cada request e injete no contexto.
Nunca passe tenant_id como parâmetro de URL visível ao usuário final.

---

## 8. Rastreabilidade jurídica — regra crítica

Todo output de pesquisa jurídica (legislação, jurisprudência, doutrina) DEVE incluir
fonte verificável. O modelo NUNCA pode inventar precedentes, valores ou citações.

Schema obrigatório para fontes jurídicas:

```python
class LegalSource(BaseModel):
    source_type: Literal["legislation", "jurisprudence", "doctrine"]
    title: str
    reference: str          # ex: "CDC art. 14, caput" ou "TJSP — AC 1234567-00"
    retrieved_at: datetime
    url: str | None         # URL da fonte quando disponível
    excerpt: str            # trecho exato — nunca parafraseado pelo modelo
    confidence: float       # 0.0 a 1.0
    verified: bool = False  # True apenas após revisão humana
    hallucination_risk: bool = False  # True se não houver fonte verificável
```

Se o modelo não encontrar fonte verificável:
- Retorne o campo com hallucination_risk = True
- Nunca preencha excerpt com texto inventado
- Sinalize ao advogado que a pesquisa precisa de verificação manual

---

## 9. CaseState — estado central do caso

Toda informação do caso trafega pelo CaseState definido em orchestrator/state.py.
Nunca passe dados soltos entre agentes. Nunca crie variáveis locais que dupliquem
campos do CaseState.

Campos obrigatórios que todo nó do grafo deve respeitar:

```
case_id          UUID — identificador único do caso
tenant_id        UUID — escritório dono do caso
status           CaseStatus — enum com todos os estados possíveis
current_module   ModuleName — módulo ativo no momento
human_approval_required  bool — se True, pausar e aguardar aprovação
approved_by      str | None — identificação do advogado aprovador
approved_at      datetime | None — timestamp da aprovação
audit_log        list[AuditEntry] — registro imutável de todas as ações
```

Ao criar um novo nó do grafo, sempre retorne um dicionário com apenas os campos
que o nó efetivamente modificou. Nunca retorne o state inteiro.

---

## 10. Auditoria — toda ação deve ser registrada

Cada nó do grafo deve registrar uma entrada no audit_log antes de retornar.

```python
class AuditEntry(BaseModel):
    timestamp: datetime       # UTC
    actor: Literal["system", "agent", "human"]
    actor_id: str             # nome do agente ou ID do usuário humano
    action: str               # descrição da ação realizada
    module: ModuleName        # módulo onde ocorreu
    input_hash: str           # SHA-256 do input recebido
    output_hash: str          # SHA-256 do output gerado
    model_used: str           # ex: "gemini-1.5-pro" ou "gpt-4o"
    tokens_used: int          # total de tokens consumidos
    duration_ms: int          # tempo de execução em milissegundos
    metadata: dict[str, Any]  # dados adicionais livres
```

Função utilitária a criar em `backend/app/core/audit.py`:

```python
def create_audit_entry(
    actor_id: str,
    action: str,
    module: ModuleName,
    input_data: Any,
    output_data: Any,
    model_used: str,
    tokens_used: int,
    duration_ms: int,
    actor: Literal["system", "agent", "human"] = "agent",
    metadata: dict | None = None,
) -> AuditEntry:
    ...
```

---

## 11. Prompts — padrões obrigatórios

- Prompts ficam em prompts/<modulo>/<agente>.md — NUNCA inline no código Python
- Carregue prompts em runtime com função utilitária em core/prompts.py
- Todo arquivo de prompt deve seguir esta estrutura:

```
<!-- v1.0 | YYYY-MM | <nome do agente> -->

# <Nome do Agente> — Prompt

## Papel
<descrição do papel do agente>

## Input esperado
<descrição do input que o agente recebe>

## Tarefa
<lista numerada das tarefas que o agente deve executar>

## Restrições
- Não invente fontes jurídicas
- Não tome decisões jurídicas autônomas
- Não afirme direitos do cliente sem base em fonte verificável
- Retorne sempre em JSON estruturado conforme o schema definido

## Output obrigatório (JSON)
<schema JSON esperado>

## Exemplos
<exemplos de input e output quando necessário>
```

- Ao alterar um prompt, incremente a versão no comentário do topo
- Nunca sobrescreva um prompt sem registrar a versão anterior em docs/adr/

---

## 12. Segurança

- Autenticação: JWT com access token (15min) + refresh token (7 dias)
- Autorização: RBAC com roles: admin | lawyer | paralegal | viewer
- Uploads: validar MIME type, tamanho máximo 50MB, armazenar em bucket privado
- Logs: nunca logar conteúdo de documentos, CPF, dados pessoais de clientes
- CORS: whitelist explícita de origens — proibido allow_origins=["*"] em produção
- Rate limiting: aplicar em todas as rotas de API via middleware FastAPI
- Variáveis sensíveis: DATABASE_URL, SECRET_KEY, API keys — nunca no código

---

## 13. Convenções de nomenclatura

| Elemento                  | Convenção                                              | Exemplo                              |
|---------------------------|--------------------------------------------------------|--------------------------------------|
| Módulos LangGraph         | snake_case com sufixo _graph                           | intake_graph, evidence_graph         |
| Nós do grafo              | verbo no infinitivo, snake_case                        | analyze_documents, route_case        |
| Rotas FastAPI             | kebab-case                                             | /api/v1/cases/{id}/run-intake        |
| Tabelas PostgreSQL        | snake_case plural                                      | cases, audit_logs, legal_sources     |
| Variáveis de ambiente     | SCREAMING_SNAKE_CASE com prefixo do serviço            | DB_HOST, OPENAI_API_KEY, REDIS_URL   |
| Modelos Pydantic          | PascalCase                                             | CaseState, LegalSource, AuditEntry   |
| Arquivos Python           | snake_case                                             | case_service.py, audit_utils.py      |
| Componentes React         | PascalCase                                             | CaseCard.tsx, ReviewPanel.tsx        |
| Hooks React               | camelCase com prefixo use                              | useCase.ts, useTenantConfig.ts       |

---

## 14. Módulos do Squad — mapeamento de agentes

Os 11 agentes do Squad Digital são implementados como 6 módulos LangGraph:

| Módulo         | Arquivo                    | Agentes que implementa              |
|----------------|----------------------------|-------------------------------------|
| intake         | graphs/intake.py           | Coordenador + Triagem               |
| evidence       | graphs/evidence.py         | Análise Documental + Especialista   |
| research       | graphs/research.py         | Legislativa + Jurisprudência + Doutrina |
| strategy       | graphs/strategy.py         | Estrategista Sênior                 |
| drafting       | graphs/drafting.py         | Esqueleto + Redator                 |
| review         | graphs/review.py           | Revisor + Aprendizado               |

Cada módulo é um StateGraph independente. O router.py encadeia os módulos
e gerencia as transições entre eles com base no status do CaseState.

---

## 15. O que nunca fazer

- Não use LangChain diretamente — use LangGraph (que já inclui o necessário)
- Não crie agentes como classes soltas fora do grafo LangGraph
- Não exponha o n8n ao frontend — ele é infraestrutura interna invisível
- Não use SQLite em nenhum ambiente — PostgreSQL sempre, inclusive em dev via Docker
- Não hardcode nomes de modelos de IA — use constantes em core/config.py
- Não gere petições em formato final — sempre DRAFT com status DRAFT_PENDING_REVIEW
- Não misture lógica de tenant em camadas de agente — isole em middleware de request
- Não faça chamadas diretas ao modelo de IA fora dos nós do grafo LangGraph
- Não crie endpoints sem autenticação JWT e verificação de role

---

## 16. Checklist ao implementar qualquer nova funcionalidade

Antes de considerar uma tarefa concluída, verifique:

- [ ] Schema Pydantic criado para input e output
- [ ] CaseState atualizado se necessário com novos campos
- [ ] Nó do grafo com type hints completos e docstring
- [ ] Entrada no audit_log registrada dentro do nó
- [ ] Filtro de tenant_id presente em todas as queries
- [ ] Prompt correspondente criado ou atualizado em prompts/
- [ ] Teste unitário escrito para o nó ou serviço
- [ ] Nenhum segredo hardcoded
- [ ] Nenhum output jurídico sem status DRAFT_PENDING_REVIEW
- [ ] Rota de API com autenticação JWT e verificação de role (se aplicável)