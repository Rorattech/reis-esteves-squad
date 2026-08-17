# ADR 0004 — Deploy: VPS Hostinger KVM 2 (São Paulo) + frontend na Netlify

- **Status:** Aceito
- **Data:** 2026-08-17
- **Fase:** Operação — primeira ida a produção
- **Relacionado:** ADR 0001 (armazenamento de evidências), ADR 0003 (OCR gerenciado
  e transferência internacional)

## Contexto

Até aqui o projeto só rodava em `docker-compose` local. A ida a produção esbarrava
em três problemas concretos do stack de desenvolvimento:

1. **`postgres`, `redis` e `n8n` publicavam portas no host** (`5432`, `6379`,
   `5678`). Em `localhost` é conveniência; numa VPS com IP público, `ports:` faz
   bind em `0.0.0.0` — banco com dados de clientes e cache exposto à internet.
2. **Os dois Dockerfiles eram de desenvolvimento.** Backend com
   `uvicorn --reload` e o código como bind mount; frontend com `npm run dev`,
   sem `next build`.
3. **Não havia reverse proxy nem TLS.** `infra/nginx.conf` era citado no
   CLAUDE.md mas nunca existiu.

Além disso, o `next build` sozinho pede ~2 GB de RAM — era o que empurrava o
dimensionamento da VPS para 8 GB mesmo com o regime cabendo em ~4,5 GB.

### Dimensionamento medido

Consumo em regime, serviço a serviço: Postgres ~1 GB, n8n ~400–600 MB, backend
~400–600 MB, Redis ~256 MB, Caddy ~50 MB, SO + daemon ~700 MB–1 GB. Total
~3–3,5 GB sem o frontend.

O perfil de CPU mudou com o ADR 0003: o tesseract era a única carga CPU-bound
real (rasterizar PDF e rodar OCR prendia o worker por minutos). Com o OCR
gerenciado, tudo que sobra é I/O-bound — Postgres, e HTTP para Vision e
Anthropic. CPU deixou de ser o gargalo.

## Decisão

### Infraestrutura

**VPS Hostinger KVM 2** — 2 vCPU, 8 GB RAM, 100 GB NVMe, datacenter em
**São Paulo**. Roda backend, Postgres, Redis, n8n e Caddy.

**Frontend na Netlify**, buildado a partir do mesmo repositório.

### Por que São Paulo, e não Hetzner

Hetzner CPX31 custa ~1/3 do preço e ainda assim foi descartada. Latência de
200–220 ms é o motivo menor. O motivo maior: hospedar o Postgres fora do Brasil
transformaria **o acervo inteiro do escritório** em transferência internacional
de dados pessoais, permanente. Hoje, depois do ADR 0003, a única saída de dados
do país é a chamada de OCR à Vision API — delimitada, por evidência, e já
documentada. Manter o banco no Brasil preserva esse escopo estreito em vez de
ampliá-lo para toda a base.

⚠️ **Armadilha de custo:** o preço contratado é promocional. A renovação de VPS
no Brasil sobe de 40% a 100%. Contratar 12 ou 24 meses trava o valor; renovar
mês a mês não.

### Repositório: monorepo, frontend e backend juntos

O frontend **não** vira projeto separado, apesar de ir para outro provedor.

`frontend/src/types/api.ts` espelha explicitamente os schemas Pydantic do
backend — o próprio arquivo documenta isso. A adição de `low_confidence`
(ADR 0003) exigiu mudar schema Pydantic, tipo TS, componente e testes no mesmo
commit. Em repositórios separados isso vira PR pareado e os tipos divergem na
primeira vez que alguém esquecer. A §16 do CLAUDE.md ainda exige entrega
vertical (backend + frontend na mesma fase) — repo único é o que torna essa
regra verificável num diff.

A Netlify lida com monorepo nativamente: *base directory* = `frontend`, e
`build.ignore` pula o build quando o commit não tocou essa pasta.

### Topologia

```
                         Internet
                            │
            ┌───────────────┴───────────────┐
            │                               │
   app.<dominio>                    api.<dominio>
   CNAME → Netlify                  A → VPS (São Paulo)
   (build + CDN)                           │
            │                          Caddy :443
            │                          (TLS automático)
            │                               │
            └──── XHR c/ Bearer ───────► backend:8000
                                             │
                          ┌──────────────────┼──────────────┐
                       postgres            redis           n8n
                     (sem porta)        (sem porta)   (sem porta, SSH)
```

Único container com porta publicada: o Caddy (80/443). Os demais só se enxergam
pela rede interna `squad-net`.

**O n8n não tem subdomínio nem entrada no proxy.** CLAUDE.md §15 é explícito
sobre ele ser infraestrutura interna invisível. Administração por túnel SSH:

```
ssh -L 5678:localhost:5678 usuario@vps   →   http://localhost:5678
```

Isso remove uma superfície de ataque inteira — o n8n guarda credenciais de
automação e a `N8N_ENCRYPTION_KEY`.

### Sem subdomínio por tenant

CLAUDE.md §7 proíbe `tenant_id` em URL visível ao usuário final, e
`escritorio1.app.<dominio>` é exatamente isso — além de exigir wildcard TLS. O
tenant continua vindo do JWT.

### DNS

| Tipo | Nome | Valor |
|---|---|---|
| CNAME | `app` | site da Netlify |
| A | `api` | IPv4 da VPS |
| CAA | `@` | `0 issue "letsencrypt.org"` |

- **Sem wildcard** — subdomínio digitado errado não deve resolver para a VPS.
- **CAA** impede emissão de certificado por qualquer CA que não a Let's Encrypt.
- **TTL 300 antes do cutover, 3600 depois** — erro se corrige em 5 minutos.
- ⚠️ **O domínio do escritório já tem e-mail.** Adicionar apenas os registros
  novos; não substituir a zona nem tocar em MX/SPF/DKIM/DMARC. Derrubar o e-mail
  de um escritório de advocacia é pior que um deploy atrasado.
- **O DNS de `api.` precisa estar propagado ANTES do primeiro `make prod-up`**,
  senão a validação da Let's Encrypt falha e o Caddy entra em retry.

## Implementação

| Arquivo | Papel |
|---|---|
| `infra/docker-compose.prod.yml` | Stack de produção — arquivo próprio, não override |
| `infra/Caddyfile` | Reverse proxy + TLS automático da API |
| `backend/Dockerfile` | Multi-stage: `target: dev` e `target: prod` |
| `frontend/netlify.toml` | Build, monorepo e headers do frontend |
| `frontend/next.config.ts` | `output: standalone` atrás de `BUILD_TARGET=docker` |
| `Makefile` | Alvos `prod-*` |

**`docker-compose.prod.yml` é um arquivo completo, não um override**: o merge do
Compose sabe adicionar, não remover — e o que precisa sumir em produção são
justamente os `ports:` e os bind mounts do dev.

**O `target` é obrigatório nos dois compose.** Sem ele, o Docker builda o último
estágio do Dockerfile, e um deploy de produção sairia com `--reload` ligado.

Decisões menores, com o motivo:

- **Caddy em vez de nginx.** Não havia `nginx.conf` a preservar, e TLS
  automático dispensa certbot + renovação em cron.
- **`--workers 2`.** Seguro porque o rate limit já usa Redis como storage
  compartilhado (`app/core/rate_limit.py`) — com storage em memória, cada worker
  teria seu próprio contador e o limite efetivo dobraria.
- **Backend não roda como root** (`appuser`, uid 10001).
- **`request_body max_size`** no Caddy: `BACKEND_MAX_UPLOAD_MB` é 50 e o
  multipart acrescenta alguns por cento; sem folga o proxy corta antes do
  backend e o advogado recebe um 413 sem explicação.
- **Volumes `caddy_data`/`caddy_config`** persistem os certificados; sem eles,
  cada recreate pede certificado novo e bate no rate limit da Let's Encrypt.

## Consequências

### Positivas

- Banco, evidências e aplicação em território nacional.
- Build do frontend sai da VPS — é o que permite a KVM 2 (8 GB) em vez de um
  plano maior, e o regime cai para ~3–3,5 GB.
- Preview deploy por branch na Netlify: a tela pode ser revisada pelo advogado
  antes do merge, sem subir nada em produção. Não existia antes.
- Rollback atômico do frontend.
- Postgres, Redis e n8n deixam de ser alcançáveis pela internet.

### Negativas

- Dois pipelines de deploy em vez de um.
- `NEXT_PUBLIC_API_URL` é embutida no build, não lida em runtime: mora nas env
  vars do site na Netlify. Esquecer faz o deploy subir **verde** e quebrar em
  runtime apontando para `localhost` — falha silenciosa.
- CORS passa a ser load-bearing (`BACKEND_CORS_ORIGINS` precisa listar
  `https://app.<dominio>`).
- Dependência de fornecedor para algo que custava ~R$ 0 a mais na VPS.

### O que a Netlify vê — e o que não vê

O frontend não tem `middleware.ts`, não tem server action e **nenhuma rota busca
dados no servidor**: as 8 páginas sem `"use client"` são um `redirect()`,
placeholders e o root layout. Toda página com dado real é client component
buscando via `api.ts` com Bearer token.

Consequência: **o conteúdo de casos, clientes e evidências nunca transita pela
Netlify.** O navegador fala direto com `api.<dominio>`, na VPS em São Paulo.
Isso é categoricamente diferente de terminar TLS num terceiro (ver a ressalva
sobre proxy da Cloudflare abaixo).

Não é literalmente zero, porém, e a precisão importa: o `next build` marca as
rotas dinâmicas (`/cases/[caseId]`, `/clients/[clientId]`,
`/cases/[caseId]/evidencias/[evidenceId]`) como `ƒ` — renderizadas sob demanda.
O **shell** dessas páginas é renderizado em função serverless da Netlify, e a
URL requisitada — que contém UUIDs de caso, cliente e evidência — chega aos
servidores dela e aos seus logs de acesso. São identificadores pseudonimizados,
sem conteúdo e **sem `tenant_id`** (que vem do JWT, nunca da URL — CLAUDE.md §7).
Exposição muito menor que conteúdo, mas não nula, e precisa constar no ROPA.

⚠️ **A armadilha a vigiar.** A Netlify hoje não vê conteúdo *porque não há SSR*.
No dia em que um server component buscar dados do caso — natural em App Router, e
provável nas Fases 5–7 (painel de estratégia, editor de minuta) — esse fetch
passa a rodar **nos servidores da Netlify**, com o conteúdo do caso junto. A
transferência internacional volta pela porta dos fundos, sem ninguém decidir.

**Regra desta decisão: o frontend permanece 100% client-side. Qualquer SSR que
toque dados de caso exige revisar este ADR.**

### Cloudflare — se entrar, entra por decisão

Se a Cloudflare for colocada na frente de `api.`, usar modo **DNS-only** (nuvem
cinza). No modo proxy o TLS termina lá, e um terceiro estrangeiro passa a ver
100% do tráfego da API descriptografado — incluindo evidências. Optar pelo WAF
mesmo assim é legítimo, mas é uma decisão de LGPD que precisa de ADR próprio,
não de um default.

### Backup — pendente

`make prod-backup` gera dump do Postgres **e** tar das evidências. Os dois
precisam ser tirados juntos: o inventário vive no banco e os originais no
volume; um sem o outro é inconsistente.

Pendências antes de dados reais:

- [ ] Agendar `make prod-backup` em cron e **enviar para fora da VPS** (backup no
      mesmo disco não protege contra perda do disco).
- [ ] Testar a restauração ao menos uma vez — backup não testado não é backup.
- [ ] Definir retenção, considerando prazos de guarda documental do escritório.
- [ ] Fechar as pendências de LGPD do ADR 0003 (a transferência do OCR é
      independente desta decisão e continua em aberto).
- [ ] Firewall da VPS liberando só 22, 80 e 443.

## Alternativas consideradas

1. **Tudo na VPS, frontend em container.** Um pipeline só, mais simples. Exigiria
   plano maior (o `next build` na VPS) ou build em CI com registry — e perderia o
   preview deploy por branch.
2. **Hetzner / DigitalOcean.** Mais baratas ou mais maduras, mas sem datacenter
   no Brasil; ampliariam a transferência internacional para toda a base.
3. **Magalu Cloud.** Única nuvem pública brasileira madura, com contratos para
   setores regulados — argumento comercial real numa venda B2B jurídica. ~4× o
   custo. Fica como caminho de migração se o porte do cliente exigir.
4. **Vercel no lugar da Netlify.** Host mais nativo para Next.js, mesmo
   enquadramento de LGPD. Netlify escolhida pelo tier gratuito mais folgado para
   o volume do MVP.
