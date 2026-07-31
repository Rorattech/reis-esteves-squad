# ADR 0003 — Escopo de RLS reaplicado por transação, com GUC LOCAL

- **Status:** Aceito
- **Data:** 2026-07-31
- **Fase:** correção de defeito (multitenancy — CLAUDE.md, seção 7)

## Contexto

`POST /api/v1/cases` respondia **HTTP 500** de forma intermitente. A exceção
era sempre a mesma:

```
sqlalchemy.exc.InvalidRequestError: Could not refresh instance '<Case ...>'
  File "/app/app/api/v1/cases.py", line 95, in create_case
    await session.refresh(case)
```

O `INSERT` era commitado com sucesso; o que falhava era o `SELECT` do
`session.refresh()` logo depois — ele voltava zero linhas, e o SQLAlchemy
traduz isso como "não consegui recarregar a instância".

A causa é a interação entre o pool de conexões e a Row Level Security:

1. O `TenantMiddleware` abria a sessão e setava `app.current_tenant` **uma
   única vez**, com `set_config(..., is_local=false)`.
2. Ao dar `commit()`, a sessão devolve a conexão física ao pool.
3. A instrução seguinte da mesma sessão (o `SELECT` do refresh) faz um novo
   checkout — e o pool, sendo FIFO, entrega uma conexão **diferente**.
4. Essa outra conexão carrega o `app.current_tenant` deixado pela última
   request que a usou. Se foi um `/auth/login`
   (`get_auth_bootstrap_session`, que seta `app.current_tenant = ''`), a
   policy `tenant_isolation` esconde a linha recém-inserida.

Reproduzido de forma determinística segurando cinco sessões de bootstrap
simultâneas (para o pool crescer) antes do insert:

```
pid antes do commit=14283  pid depois=14285  guc depois=''
refresh FALHOU -> InvalidRequestError Could not refresh instance
```

O 500 era o sintoma visível, mas o problema é mais amplo: **qualquer query
emitida depois de um `commit()` dentro da mesma request rodava sem o escopo
de tenant correto**, e o padrão `commit()` + `refresh()` aparece em mais de
dez pontos do backend (`app/api/v1/cases.py`, `app/services/*`).

Alternativas consideradas:

1. **Remover o `session.refresh()` das rotas** — some o sintoma em
   `create_case` e mantém o defeito em todos os outros call sites; qualquer
   leitura pós-commit continuaria sem tenant.
2. **`expire_on_commit` / segurar a transação aberta pela request inteira** —
   prenderia uma conexão por request durante todo o handler, inclusive em
   tarefas longas, e não resolve `tenant_scoped_session` (background).
3. **Reaplicar o escopo no início de cada transação**, via evento
   `after_begin` do SQLAlchemy.

## Decisão

Adotar a alternativa 3, em `app/core/db.py`:

- O escopo de RLS deixa de ser um `execute()` avulso e passa a ser **declarado
  em `session.info`**, por `scope_session_to_tenant(session, tenant_id)` ou
  `scope_session_to_auth_bootstrap(session)`.
- O listener `_apply_rls_scope` (evento `after_begin` da `Session`) aplica
  `app.current_tenant`/`app.bootstrap` **no início de toda transação** da
  sessão — inclusive nas que começam depois de um `commit()`, em outra
  conexão física.
- As GUCs passam a ser **LOCAL** (`set_config(..., true)`): morrem com a
  transação, então nenhum valor de tenant sobrevive na conexão devolvida ao
  pool. O envenenamento entre requests deixa de existir na origem, em vez de
  ser compensado depois.
- Uma sessão que não declara escopo nenhum (ex.: `get_session`, usada só em
  rotas públicas) recebe "sem tenant, sem bootstrap" — o default é fechado,
  nunca o resíduo da request anterior.

## Consequências

**Positivas**

- O 500 em `POST /cases` desaparece, e junto com ele a classe inteira de bugs
  de "query pós-commit sem tenant" — sem alterar nenhum dos call sites de
  `commit()` + `refresh()`.
- O isolamento por tenant fica mais forte que antes: com GUC LOCAL, uma
  conexão devolvida ao pool não carrega mais o tenant da request anterior.
- O escopo vira declarativo e auditável em um ponto só, em vez de um
  `set_config` repetido em cada abertura de sessão.

**Negativas / limites**

- Custo de um `SELECT set_config(...)` por transação (antes: por sessão). É
  uma ida ao banco a mais por transação, sem round-trip extra perceptível
  frente ao restante da query.
- O listener é registrado na classe `Session` do SQLAlchemy, ou seja, vale
  para toda sessão criada no processo. É intencional (fail closed), mas
  significa que código que dependa de setar a GUC "na mão" via
  `session.execute(...)` deixa de funcionar: o listener já aplicou o escopo
  LOCAL da transação e ele prevalece. Todo o uso no repositório foi migrado
  para os helpers (`backend/tests/*`, `app/middleware/tenant.py`).
- Conexões obtidas fora de uma `Session` (ex.: Alembic, que roda com o papel
  dono das tabelas) não passam pelo listener — continuam responsabilidade de
  quem as abre.

## Regressão coberta

`backend/tests/test_tenant_isolation.py::test_tenant_scope_is_reapplied_after_commit_on_another_connection`
recria o cenário (pool envenenado por sessões de bootstrap → insert → commit →
refresh) e falha sem esta correção.
