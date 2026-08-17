# Runbook — Primeiro deploy em produção

Passo a passo operacional para colocar o Squad Digital no ar: domínio, VPS
Hostinger, DNS, backend e frontend na Netlify.

**A decisão e o porquê de cada escolha estão em
[ADR 0004](adr/0004-deploy-hostinger-netlify.md).** Este documento é só a
execução.

> ⚠️ **Antes de começar:** este runbook coloca a infraestrutura de pé. Ele **não**
> libera o uso com dados reais de clientes — as pendências de LGPD do
> [ADR 0003](adr/0003-ocr-google-cloud-vision.md) (transferência internacional do
> OCR) e o backup testado da Fase 8 precisam estar fechados antes disso. Até lá,
> use apenas evidências fictícias.

## Ordem importa

Uma dependência não-óbvia governa a sequência: **o DNS de `api.` precisa estar
propagado antes de subir o stack**, porque o Caddy valida o certificado com a
Let's Encrypt no primeiro boot. Subir antes deixa o Caddy em retry e, se você
insistir, bate no rate limit da Let's Encrypt (5 falhas por hora, por domínio).

```
1. Domínio  →  2. VPS  →  3. DNS api.  →  4. Backend
                                              ↓
                          6. DNS app.  ←  5. Netlify  →  7. CORS  →  8. Verificar
```

---

## Fase 1 — Domínio

**Se o escritório já tem domínio, pule para a Fase 2** e use o domínio existente
(vamos só adicionar dois subdomínios).

### 1.1 `.adv.br` exige OAB ativa

Domínios `.adv.br` são restritos: o Registro.br valida eletronicamente a
inscrição na OAB. Advogado com inscrição suspensa, cancelada ou irregular não
consegue concluir o registro.

| Titular | O que precisa |
|---|---|
| Advogado (PF) | CPF + número de inscrição na OAB |
| Sociedade de advogados (PJ) | CNPJ + número de registro da sociedade na seccional |

**Registre em nome da sociedade (PJ)**, não de um sócio pessoa física — domínio
no CPF de um sócio vira problema societário na primeira mudança de quadro.

### 1.2 Registrar

1. Verifique disponibilidade em <https://registro.br>
2. Crie a conta com o CNPJ da sociedade
3. Registre o domínio informando o número da OAB
4. Aguarde a validação — pode levar de horas a alguns dias se pedirem documento
   complementar

⏱️ **Comece por aqui.** É a única etapa que depende de terceiro e não tem prazo
garantido. Enquanto valida, siga a Fase 2.

---

## Fase 2 — VPS Hostinger

### 2.1 Contratar

No <https://hpanel.hostinger.com>:

| Campo | Valor |
|---|---|
| Plano | **KVM 2** — 2 vCPU, 8 GB RAM, 100 GB NVMe |
| Localização | **Brasil — São Paulo** |
| Sistema | **Ubuntu 24.04 LTS** (limpo, sem painel) |
| Período | **12 ou 24 meses** |

Três observações:

- **A localização é escolhida na compra e não muda depois.** São Paulo não é
  preferência de latência: é o que mantém o banco em território nacional (ADR 0004).
- **Ubuntu 24.04 LTS**, não 26.04. O 26.04 saiu em abril/2026 e o point release
  `.1` em 06/08/2026 — maduro demais recente para um sistema jurídico em
  produção. O 24.04 tem suporte até 2029.
- **Não use template com painel** (CyberPanel, Plesk). Eles instalam nginx/Apache
  nas portas 80/443 e conflitam com o Caddy. Ubuntu limpo.
- **12/24 meses trava o preço promocional.** Renovação mês a mês sobe de 40% a 100%.

### 2.2 Chave SSH

Na sua máquina (não na VPS):

```bash
ssh-keygen -t ed25519 -C "deploy-squad-digital" -f ~/.ssh/squad_digital
cat ~/.ssh/squad_digital.pub
```

Cole a **pública** no hPanel → VPS → Manage → SSH Keys. Nunca a privada.

Conecte:

```bash
ssh -i ~/.ssh/squad_digital root@<IP-DA-VPS>
```

### 2.3 Endurecer o servidor

Tudo abaixo roda **na VPS**, como root.

**Usuário sem root:**

```bash
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
```

**Fechar login por senha e por root** — edite `/etc/ssh/sshd_config`:

```
PermitRootLogin no
PasswordAuthentication no
```

```bash
systemctl restart ssh
```

> ⚠️ **Não feche a sessão atual ainda.** Abra um segundo terminal e confirme que
> `ssh -i ~/.ssh/squad_digital deploy@<IP>` funciona. Se errar aqui e fechar a
> sessão, você se tranca fora e precisa do console de recuperação do hPanel.

**Firewall:**

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status
```

> ⚠️ **Armadilha Docker + UFW:** o Docker escreve regras de iptables que
> **passam por cima do UFW** para portas publicadas com `ports:`. No nosso
> `docker-compose.prod.yml` só o Caddy publica (80/443), que é justamente o que
> deve ser público — então estamos cobertos. Mas se alguém adicionar um `ports:`
> em Postgres ou Redis "só para depurar", a porta fica exposta à internet
> **mesmo com o UFW bloqueando**. Nunca adicione `ports:` no arquivo de produção.

**fail2ban** (barra força-bruta no SSH):

```bash
apt update && apt install -y fail2ban
systemctl enable --now fail2ban
```

### 2.4 Docker

```bash
apt install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker deploy
```

Reconecte como `deploy` e confirme:

```bash
docker compose version
```

### 2.5 Clonar o repositório

O repositório é privado, então a VPS precisa de uma **deploy key** própria — não
reutilize sua chave pessoal.

Como `deploy`, na VPS:

```bash
ssh-keygen -t ed25519 -C "vps-squad-digital" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

No GitHub: repositório → **Settings → Deploy keys → Add deploy key**. Cole a
pública, **deixe "Allow write access" desmarcado** (a VPS só precisa ler).

```bash
git clone git@github.com:<org>/reis-esteves-squad.git
cd reis-esteves-squad
```

### 2.6 Criar o `.env` de produção

> ⚠️ **Não copie o `.env` de desenvolvimento.** Ele tem `changeme_...` em toda
> senha. Gere segredos novos.

```bash
cp .env.example .env
# Gere um valor DIFERENTE para cada segredo:
openssl rand -hex 32
```

Preencha no `.env`:

| Variável | Como preencher |
|---|---|
| `POSTGRES_ADMIN_PASSWORD`, `DB_PASSWORD`, `REDIS_PASSWORD`, `N8N_DB_PASSWORD`, `N8N_BASIC_AUTH_PASSWORD` | um `openssl rand -hex 32` para cada |
| `BACKEND_SECRET_KEY`, `N8N_ENCRYPTION_KEY` | um `openssl rand -hex 32` para cada |
| `DATABASE_URL` | `postgresql+asyncpg://squad_app:<DB_PASSWORD>@postgres:5432/squad_digital` |
| `REDIS_URL` | `redis://:<REDIS_PASSWORD>@redis:6379/0` |
| `BACKEND_ENV` | `production` |
| `API_DOMAIN` | `api.<seu-dominio>` |
| `ACME_EMAIL` | e-mail real de TI (avisos de expiração de certificado) |
| `BACKEND_WORKERS` | `2` |
| `GOOGLE_VISION_API_KEY` | a chave restrita à Vision API (ADR 0003) |
| `BACKEND_CORS_ORIGINS` | `https://app.<seu-dominio>` |
| `N8N_PROTOCOL` | `https` |

```bash
chmod 600 .env
```

`DATABASE_URL` e `REDIS_URL` precisam repetir a senha que você acabou de gerar —
é o erro mais comum aqui, e o sintoma é o backend não conectar no boot.

---

## Fase 3 — DNS de `api.` (antes de subir!)

No painel de DNS do domínio (Registro.br → **Configurar endereçamento → Modo
avançado**, ou no provedor de DNS que você usa):

| Tipo | Nome | Valor | TTL |
|---|---|---|---|
| A | `api` | IPv4 da VPS | 300 |

Deixe o **TTL em 300** durante o cutover — erro se corrige em 5 minutos em vez
de uma hora. Suba para 3600 depois que estabilizar.

**Registro CAA** (opcional, recomendado) — impede que qualquer CA que não a
Let's Encrypt emita certificado para o domínio:

| Tipo | Nome | Valor |
|---|---|---|
| CAA | `@` | `0 issue "letsencrypt.org"` |

Nem todo painel suporta CAA; se o Registro.br não oferecer o tipo, siga sem ele.

> ⚠️ **Não mexa em MX, SPF, DKIM ou DMARC.** O domínio do escritório
> provavelmente já tem e-mail. Adicione **só** os registros novos; não substitua
> a zona. Derrubar o e-mail de um escritório de advocacia é pior que um deploy
> atrasado.

**Espere propagar** antes de seguir:

```bash
dig +short api.<seu-dominio>
```

Só avance quando isso devolver o IP da VPS.

---

## Fase 4 — Backend na VPS

Na VPS, dentro do repositório:

```bash
make prod-up
```

Builda as imagens e sobe backend, Postgres, Redis, n8n e Caddy. O primeiro build
leva alguns minutos.

Acompanhe o Caddy emitindo o certificado:

```bash
make prod-logs
```

Procure por `certificate obtained successfully`. Se aparecer erro de ACME, o DNS
ainda não propagou — pare (`make prod-down`), espere e suba de novo.

**Migrations:**

```bash
make prod-migrations
```

**Verifique:**

```bash
curl -i https://api.<seu-dominio>/health
```

Esperado: `HTTP/2 200`.

**Confirme que o banco NÃO está exposto** — este teste valida a correção mais
importante do ADR 0004. Rode **da sua máquina**, não da VPS:

```bash
nc -zv <IP-DA-VPS> 5432
nc -zv <IP-DA-VPS> 6379
nc -zv <IP-DA-VPS> 5678
```

Os três devem **falhar** (`Connection refused` ou timeout). Se algum conectar,
sobrou um `ports:` no compose de produção — corrija antes de seguir.

---

## Fase 5 — Frontend na Netlify

1. <https://app.netlify.com> → **Add new site → Import an existing project**
2. Conecte o GitHub e escolha o repositório
3. Configure:

| Campo | Valor |
|---|---|
| **Base directory** | `frontend` |
| Build command | `npm run build` *(já vem do `netlify.toml`)* |
| Publish directory | `.next` *(idem)* |

4. **Environment variables** → adicione:

```
NEXT_PUBLIC_API_URL = https://api.<seu-dominio>/api/v1
```

> ⚠️ Esta variável é **embutida no bundle em tempo de build**, não lida em
> runtime. Se esquecer, o deploy sobe **verde** e quebra no navegador apontando
> para `localhost`. E se mudar depois, precisa **redeployar** — alterar a
> variável sozinha não muda o bundle já publicado.

5. **Deploy site**

---

## Fase 6 — DNS de `app.`

No painel do domínio:

| Tipo | Nome | Valor | TTL |
|---|---|---|---|
| CNAME | `app` | `<site>.netlify.app` | 300 |

Na Netlify: **Domain management → Add a domain** → `app.<seu-dominio>`. Ela
detecta o CNAME e emite o certificado automaticamente.

---

## Fase 7 — Fechar o CORS

Com os dois domínios definitivos no ar, confirme no `.env` da VPS:

```
BACKEND_CORS_ORIGINS=https://app.<seu-dominio>
```

E recarregue o backend:

```bash
make prod-up
```

Sem isso, o navegador bloqueia toda chamada do frontend para a API — o sintoma é
a tela carregar e nenhum dado aparecer, com erro de CORS no console.

---

## Fase 8 — Verificação e operação

### 8.1 Checklist de fumaça

- [ ] `https://app.<dominio>` carrega a tela de login
- [ ] Login funciona (token chega, redireciona para `/cases`)
- [ ] Criar um caso de teste funciona
- [ ] Upload de uma imagem de evidência → status vai para `processed`
- [ ] O texto extraído aparece com o aviso de conteúdo derivado *(valida a Vision API)*
- [ ] Download do original funciona
- [ ] `nc -zv <IP> 5432` falha
- [ ] `https://api.<dominio>/health` responde 200 com certificado válido

### 8.2 Backup — obrigatório antes de dados reais

`make prod-backup` gera dump do Postgres **e** tar das evidências. Os dois saem
juntos de propósito: o inventário vive no banco, os originais no volume — um sem
o outro é inconsistente.

Agende (`crontab -e` como `deploy`), 3h da manhã:

```
0 3 * * * cd /home/deploy/reis-esteves-squad && make prod-backup >> /home/deploy/backup.log 2>&1
```

> ⚠️ **Isso ainda não é backup.** Grava no mesmo disco da VPS — não protege
> contra perda do disco, que é o cenário que mais importa. Falta:
>
> - [ ] Enviar os arquivos para **fora da VPS** (object storage, outro servidor)
> - [ ] **Testar a restauração** ao menos uma vez — backup não testado não é backup
> - [ ] Definir retenção, considerando os prazos de guarda documental do escritório

### 8.3 Acessar o n8n

Não tem subdomínio, por decisão (CLAUDE.md §15). Da sua máquina:

```bash
ssh -i ~/.ssh/squad_digital -L 5678:localhost:5678 deploy@<IP-DA-VPS>
```

Com o túnel aberto, acesse `http://localhost:5678`.

### 8.4 Estabilizar o DNS

Passados alguns dias sem incidente, suba o TTL de `api` e `app` de 300 para 3600.

---

## Deploys seguintes

**Frontend:** automático. Push na branch de produção → Netlify builda. Commits
que não tocam `frontend/` são ignorados (`build.ignore` no `netlify.toml`).

**Backend:** na VPS,

```bash
cd ~/reis-esteves-squad
git pull
make prod-up
make prod-migrations   # só se houver migration nova
```

**Rollback do frontend:** Netlify → Deploys → escolher o anterior → *Publish
deploy*. Instantâneo.

**Rollback do backend:** `git checkout <commit-anterior>` e `make prod-up`.
Atenção: migration aplicada **não** volta sozinha — verifique se o commit
anterior é compatível com o schema atual antes de reverter.

---

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| Caddy em retry, sem certificado | DNS de `api.` não propagou antes do `prod-up` |
| Frontend carrega, nenhum dado aparece | `BACKEND_CORS_ORIGINS` não lista `https://app.<dominio>` |
| Frontend chama `localhost` | `NEXT_PUBLIC_API_URL` faltando na Netlify, ou mudou sem redeploy |
| Backend não sobe, erro de conexão | Senha em `DATABASE_URL`/`REDIS_URL` diverge da senha gerada |
| 413 no upload de evidência | `BACKEND_MAX_UPLOAD_MB` não chegou ao Caddy (`request_body max_size`) |
| OCR falha em toda imagem | `GOOGLE_VISION_API_KEY` ausente ou sem a Vision API habilitada |
| Netlify nunca builda | `build.ignore` — confira o pathspec ancorado `':/frontend'` |
