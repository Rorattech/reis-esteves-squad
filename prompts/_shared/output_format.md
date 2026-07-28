---
version: 1.0.0
squad: shared
module: all
agent: output_format
last_updated: 2025-01-01
---

# Formato de Output Padrão — Reis Esteves Advocacia

## Estrutura Obrigatória de Relatório

Todo agente DEVE produzir um relatório neste formato exato:

=== RELATÓRIO: [NOME DO AGENTE] — [ÁREA] ===
Processo: [Cliente / Matéria]
Data: [Data]
Etapa: [Etapa atual]
Status: CONCLUÍDO | EM ANDAMENTO | BLOQUEADO

[CONTEÚDO DO RELATÓRIO]

Próxima etapa: [nome da próxima etapa]
Encaminhar para: [Agente responsável]


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