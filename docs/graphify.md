# Graphify — grafo de conhecimento do projeto

O Graphify indexa o repositório inteiro (código + docs) em um grafo de conhecimento
persistido em `graphify-out/graph.json`. O Claude Code consulta esse grafo antes de
sair lendo arquivo por arquivo, o que reduz drasticamente o consumo de contexto em
perguntas sobre arquitetura, dependências e impacto de mudanças.

Versão instalada: `graphifyy` 0.9.32 (via pipx).

---

## 1. Setup para um novo dev na equipe

```bash
# 1. instalar a CLI
pipx install graphifyy
pipx inject graphifyy openai watchdog   # backend Gemini + modo watcher

# 2. configurar a chave da API (fora do repositório)
mkdir -p ~/.graphify
cat > ~/.graphify/env <<'EOF'
export GEMINI_API_KEY="<sua-chave>"
export GRAPHIFY_GEMINI_MODEL="gemini-3-flash-preview"
EOF
chmod 600 ~/.graphify/env

# 3. carregar no shell (~/.zshrc ou ~/.bashrc)
echo '[ -f "$HOME/.graphify/env" ] && source "$HOME/.graphify/env"' >> ~/.zshrc

# 4. integrar ao Claude Code + hooks de git
graphify install --platform claude   # skill global em ~/.claude/skills/graphify
graphify hook install                # post-commit / post-checkout + merge driver
```

> **Não rode `graphify claude install` neste repositório.** A seção do `CLAUDE.md`
> e os hooks `PreToolUse` já estão versionados e funcionam para toda a equipe. Esse
> comando reescreve o `.claude/settings.json` gravando o caminho absoluto do binário
> da *sua* máquina (`/home/<você>/.local/bin/graphify`), o que quebra o hook para
> todos os outros devs no próximo `pull`. Ver a seção 7.

> A chave **nunca** entra no repositório. Ela vive em `~/.graphify/env` com permissão
> `600`, seguindo a seção 12 do `CLAUDE.md` (nenhum segredo hardcoded).

---

## 2. O que está versionado

| Caminho | Versionado? | Motivo |
|---------|-------------|--------|
| `graphify-out/graph.json` | **sim** | o grafo em si — quem der `pull` já recebe pronto, sem gastar cota de API |
| `graphify-out/cache/`, `manifest.json`, `.graphify_*` | não | artefatos locais de cache/incremental |
| `graphify-out/graph.html`, `GRAPH_REPORT.md` | não | derivados, regeráveis a partir do `graph.json` |
| `.gitattributes` | sim | registra o merge driver do `graph.json` |
| `.claude/settings.json` | sim | hooks PreToolUse compartilhados pela dupla |
| `.claude/hooks/graphify-guard.sh` | sim | resolve o binário do graphify por máquina |
| `~/.graphify/env` | **nunca** | contém a chave da API |

### Por que existe o `graphify-guard.sh`

O que é versionado precisa valer para todas as máquinas; o caminho do binário do
graphify não vale. O `settings.json` chama sempre o mesmo wrapper relativo ao
projeto:

```json
"command": "sh \"${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/graphify-guard.sh\" search"
```

e o wrapper procura o `graphify` no `PATH`, depois nos caminhos típicos de
instalação (`~/.local/bin`, venv do pipx, `/usr/local/bin`, `/opt/homebrew/bin`).
Se não achar nenhum, **sai com código 0 e sem mensagem** — quem ainda não instalou
a CLI simplesmente trabalha sem o enriquecimento de contexto, em vez de tomar erro
de hook a cada comando.

Para desligar o hook pontualmente, sem editar nada: `GRAPHIFY_HOOK_DISABLE=1`.

### Merge driver

`.gitattributes` contém:

```
graphify-out/graph.json merge=graphify
```

Quando os dois lados regeram o grafo, o Git chamaria um conflito em um JSON de ~1,3 MB.
O merge driver do Graphify faz **union merge** dos nós e edges em vez de conflito.

O driver é registrado no `.git/config` local de cada máquina — por isso cada dev
precisa rodar `graphify hook install` uma vez. Sem isso, o merge do `graph.json`
vira conflito manual (a solução nesse caso é simplesmente rodar `graphify update .`
e usar o resultado).

---

## 3. Uso no dia a dia

### Consultas (o que o Claude usa)

```bash
graphify query "como o tenant_id é propagado nas queries?"
graphify path "CaseState" "audit_log"      # caminho mais curto entre dois conceitos
graphify explain "intake_graph"            # nó + vizinhança em linguagem natural
graphify affected "CaseState"              # o que quebra se eu mexer nisso
graphify god-nodes --top 15                # hubs arquiteturais do projeto
```

### Manter o grafo atualizado

| Comando | Custo | Quando |
|---------|-------|--------|
| `graphify update .` | **grátis** (AST local, sem LLM) | depois de mexer em código |
| `graphify extract . --backend gemini` | ~$0.04 | depois de mexer em `.md` / docs |
| `graphify watch .` | grátis para código | durante uma sessão de trabalho |
| `graphify cluster-only .` | LLM só para nomear comunidades | regerar `GRAPH_REPORT.md` |

Os hooks `post-commit` e `post-checkout` já rodam a atualização automaticamente a
cada commit e a cada troca de branch — na prática você raramente roda isso à mão.

### Modo watcher

```bash
graphify watch .
```

Fica observando o repositório e rebuilda o grafo a cada mudança de código
(AST-only, sem custo de API, debounce de 3s). Mudanças em **documentos** não são
reprocessadas automaticamente — o watcher grava um flag `needs_update` e avisa;
aí você roda `graphify extract . --backend gemini`.

---

## 4. Fluxo em dupla (push/pull)

```
dev A: commit  → post-commit atualiza graph.json → push
dev B: pull    → merge driver resolve graph.json  → post-checkout atualiza
```

Regras práticas:

- **Não** resolva conflito de `graph.json` na mão. Se aparecer um, rode
  `graphify update .` e comite o resultado — o grafo é derivado do código.
- Trocou de branch e o grafo parece velho? `graphify update .` resolve em segundos.
- Refatorou apagando muito código? Use `graphify update . --force` — sem o `--force`
  o Graphify se recusa a sobrescrever um grafo por outro com menos nós (proteção
  contra rebuild parcial).

---

## 5. Integração com o Claude Code

Dois mecanismos, ambos instalados:

1. **Skill** (`~/.claude/skills/graphify/SKILL.md`) — ensina o Claude a usar
   `query` / `path` / `explain` e responde ao comando `/graphify`.
2. **Hooks PreToolUse** (`.claude/settings.json`) — antes de `Bash|Grep` e
   `Read|Glob`, injetam o contexto relevante do grafo. Modo **normal**: nunca
   bloqueiam a ferramenta, apenas enriquecem o contexto.

Para endurecer (bloquear a primeira leitura crua por sessão, forçando consulta ao
grafo antes): `graphify claude install --strict`, ou `GRAPHIFY_HOOK_STRICT=1` em
runtime sem reinstalar. Para desligar: `graphify claude uninstall`.

---

## 6. Limitações conhecidas neste repositório

- `settings.json` produz zero nós (é config, não código) — esperado.
- Alguns `.md` longos ocasionalmente voltam vazios da extração semântica; uma
  re-execução de `graphify extract .` os reprocessa.
- O grafo indexa **estrutura**, não semântica jurídica. Ele não substitui o
  `CLAUDE.md` nem os prompts em `prompts/` como fonte de regras de negócio.

---

## 7. Problemas comuns

### `PreToolUse:Bash hook error ... /home/<alguem>/.local/bin/graphify: not found`

Alguém rodou `graphify claude install` e comitou o `.claude/settings.json` com o
caminho absoluto da própria máquina. Corrija restaurando o wrapper:

```json
"command": "sh \"${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/graphify-guard.sh\" search"
"command": "sh \"${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/graphify-guard.sh\" read"
```

O erro é **não bloqueante**: o Claude continua funcionando, apenas sem o contexto
do grafo. Mas polui toda chamada de ferramenta, então vale corrigir na hora.

### `graphify: command not found` ao rodar `make graph-update`

A CLI não está instalada nessa máquina. Rode o passo 1 da seção 1. O grafo em si
(`graphify-out/graph.json`) vem pelo `pull` e o Claude consegue lê-lo, mas sem a
CLI você não consegue nem consultar (`query`/`path`/`explain`) nem atualizar.

### Conflito no `graphify-out/graph.json`

Você não rodou `graphify hook install` nesta máquina — o merge driver mora no
`.git/config` local e não viaja pelo `push`. Resolva com `graphify update .` e
comite o resultado; depois instale o driver para não repetir.

### O hook dispara mas o `graphify query` falha

Provável falta da chave da API. Confira `~/.graphify/env` (seção 1, passo 2) e se
o seu shell realmente carrega o arquivo (`echo $GEMINI_API_KEY`). Note que
`query`/`path`/`explain` sobre um grafo já construído não custam API — só a
extração semântica (`extract`, `cluster-only`) precisa da chave.
