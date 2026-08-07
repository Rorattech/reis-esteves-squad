---
version: 1.1.0
squad: shared
module: all
agent: output_format
last_updated: 2026-08-07
---

# Formato de Output Padrão — Reis Esteves Advocacia

## Estrutura Obrigatória de Relatório

Todo agente DEVE produzir um relatório neste formato exato:

=== RELATÓRIO: [NOME DO AGENTE] — [ÁREA] ===
Processo: [Código do caso / Matéria]
Data: [Data]
Etapa: [Etapa atual]
Status: CONCLUÍDO | EM ANDAMENTO | BLOQUEADO

[CONTEÚDO DO RELATÓRIO]

Próxima etapa: [nome da próxima etapa]
Encaminhar para: [Agente responsável]


### Identificação do processo — regra de privacidade

O campo `Processo:` usa o **código do caso** (ex.: `CAS-2026-000123`), recebido
no input como `case_code` — **nunca o nome do cliente**. Nome, CPF, RG e
endereço completo não são enviados aos agentes: o sistema identifica o caso
pelo código, e a ligação entre código e pessoa vive apenas no banco do
escritório (CLAUDE.md, seção 12).

Quando o input trouxer `client_city`/`client_state`, use-os apenas para o que
depende da comarca (ex.: foro competente). Se não vierem, declare a comarca
como pendente — nunca a deduza.


## Regra de Escalada Crítica

Se identificar prazo vencendo, irregularidade grave ou oportunidade excepcional:

🚨 ALERTA CRÍTICO: [Descrição]
Prazo: [Data se houver]
Ação necessária: [O que fazer]


## Regras Gerais de Output

- Nenhuma etapa pode ser pulada. Se a anterior não estiver completa, retorne ao agente responsável.
- Status BLOQUEADO deve sempre indicar o motivo e o que é necessário para desbloquear.
- Toda afirmação jurídica deve ter fundamentação (lei, súmula ou jurisprudência).
- Outputs sem fonte verificável são inválidos.