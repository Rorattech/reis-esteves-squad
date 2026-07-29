# Carregador de prompts versionados (`backend/app/core/prompts.py`)

Documentação da API interna do carregador de prompts (Fase 2.2, ver
`docs/roadmap_mvp_squad_digital.md`). Implementa CLAUDE.md, seção 11: nenhum
nó de grafo deve montar prompt inline em Python nem ler `prompts/`
diretamente — sempre via este módulo.

Esta etapa **não chama nenhum modelo de IA** — só carrega, valida e monta o
prompt final de forma auditável. A chamada ao LLM é responsabilidade dos nós
do grafo (Fase 2.3), que devem consumir esta API em vez de reimplementá-la.

## Composição

Todo prompt final é a concatenação, nesta ordem fixa, de 4 camadas:

1. `prompts/_shared/_base.md` — instruções comuns a todos os squads. Única
   exceção sem front matter YAML (CLAUDE.md, seção 11).
2. `prompts/_shared/output_format.md` — formato padrão de output.
3. `prompts/{squad}/_squad.md` — contexto e regras do squad.
4. `prompts/{squad}/{module}/{agent}.md` — prompt específico do agente.

Para o MVP, o único `squad` suportado é `"digital"`, e `module` é um dos 6
módulos LangGraph (`intake`, `evidence`, `research`, `strategy`, `drafting`,
`review`).

## API pública

### `load_prompt(squad, module, agent) -> str`

Atalho mais comum: retorna só o texto final, pronto para enviar ao modelo.
Internamente é `load_prompt_bundle(...).text`.

### `load_prompt_bundle(squad, module, agent) -> PromptBundle`

Use esta função (em vez de `load_prompt`) sempre que o chamador precisar
**registrar em audit_log qual versão/hash de cada camada foi usada** — isto
é, todo nó de grafo que efetivamente for chamar um LLM (Fase 2.3). Retorna:

```python
class PromptBundle(BaseModel):
    text: str                        # prompt final composto
    layers: list[PromptLayerInfo]    # proveniência das 4 camadas, nesta ordem

class PromptLayerInfo(BaseModel):
    layer: Literal["base", "output_format", "squad_context", "agent"]
    path: str            # relativo a prompts_dir_path, ex.: "digital/intake/coordinator.md"
    version: str | None  # None só para "base" (_base.md não tem front matter)
    content_hash: str    # SHA-256 (hex) do conteúdo bruto do arquivo
```

### `build_prompt_audit_metadata(bundle) -> dict`

Converte um `PromptBundle` no formato esperado pelo parâmetro `metadata=` de
`create_audit_entry` (`app/core/audit.py`, CLAUDE.md seção 10):

```json
{
  "prompts": [
    {"layer": "base", "path": "_shared/_base.md", "version": null, "content_hash": "…"},
    {"layer": "output_format", "path": "_shared/output_format.md", "version": "1.0.0", "content_hash": "…"},
    {"layer": "squad_context", "path": "digital/_squad.md", "version": "1.0.0", "content_hash": "…"},
    {"layer": "agent", "path": "digital/intake/coordinator.md", "version": "1.0.0", "content_hash": "…"}
  ]
}
```

Uso esperado num nó de grafo (Fase 2.3):

```python
bundle = load_prompt_bundle("digital", "intake", "coordinator")
# ... chamada ao LLM usando bundle.text ...
audit_entry = create_audit_entry(
    actor_id="coordinator",
    action="classificou a plataforma ré",
    module="intake",
    input_data=...,
    output_data=...,
    model_used=settings.<constante_do_modelo>,
    tokens_used=...,
    duration_ms=...,
    metadata=build_prompt_audit_metadata(bundle),
)
```

O hash nunca é do prompt final concatenado — é por camada, para que uma
mudança em `_squad.md` (por exemplo) seja distinguível de uma mudança no
prompt do agente, mesmo que ambas tenham acontecido na mesma versão semver.

### `load_agent_document(squad, module, agent) -> PromptDocument`

Carrega e valida só o arquivo do agente (sem compor as outras 3 camadas) —
útil para inspecionar/testar metadados (versão, `last_updated`, hash) de um
prompt isoladamente.

```python
class PromptDocument(BaseModel):
    front_matter: PromptFrontMatter
    body: str
    path: str            # relativo a prompts_dir_path
    content_hash: str    # SHA-256 (hex) do arquivo bruto (front matter + corpo)
```

### `PromptFrontMatter`

Schema do cabeçalho YAML obrigatório (CLAUDE.md, seção 11):

```python
class PromptFrontMatter(BaseModel):
    version: str        # semver estrito: precisa casar com ^\d+\.\d+\.\d+$
    squad: str
    module: str
    agent: str
    last_updated: date  # formato YYYY-MM-DD
```

### `PromptLoadError`

Única exceção levantada por qualquer falha do carregador — nunca há
fallback silencioso. Cobre:

- Arquivo ausente (qualquer uma das 4 camadas).
- Front matter ausente, sem delimitador de fechamento, ou inválido (inclui
  `version` fora do padrão semver).
- Front matter cujo `squad`/`module`/`agent` não bate com o que foi pedido.
- `squad` fora da allowlist (hoje só `"digital"`), `module` fora dos 6
  módulos válidos, ou `agent` que não seja um identificador `snake_case`
  simples (sem `/`, `..` ou maiúsculas).

## Segurança: nunca um caminho vindo do usuário

`squad` e `module` são restritos a allowlists fechadas
(`_ALLOWED_SQUADS`/`_ALLOWED_MODULES`), e `agent` precisa casar com
`^[a-z][a-z0-9_]*$` — isso já impede qualquer tentativa de path traversal
(`agent="../../etc/passwd"` nunca chega a virar um `Path`). Como segunda
camada de defesa, `_resolve_agent_path` resolve o caminho final e confirma
que ele continua dentro de `settings.prompts_dir_path` antes de qualquer
leitura de disco — protege mesmo que uma allowlist futura seja relaxada por
engano.

Nenhuma função pública aceita um caminho de arquivo (`Path`/`str` de
caminho) como argumento — apenas os identificadores `squad`/`module`/`agent`.

## Cache

Os arquivos compartilhados (`_base.md`, `output_format.md`, `_squad.md` por
squad) são cacheados em processo via `functools.lru_cache` — eles mudam raramente
e são lidos em toda chamada de `load_prompt`/`load_prompt_bundle`. O prompt do
agente não é cacheado (é o arquivo com maior chance de mudar durante o
desenvolvimento). Reiniciar o processo invalida o cache; não há invalidação
em runtime porque prompts são versionados por arquivo + deploy, não editados
a quente em produção.

## Testes

- `backend/tests/test_prompts.py` — composição das 4 camadas para todos os
  12 agentes do squad `digital`, seções obrigatórias do corpo, e falhas de
  arquivo ausente/diretório errado.
- `backend/tests/test_prompts_audit.py` — hash determinístico e distinto por
  arquivo, `PromptBundle`/`build_prompt_audit_metadata`, validação semver de
  `version`, rejeição de path traversal e de squad/module desconhecidos, e um
  teste de ponta a ponta persistindo `build_prompt_audit_metadata(...)` numa
  linha real de `audit_logs` via `create_audit_entry`/`audit_entry_to_orm`.
