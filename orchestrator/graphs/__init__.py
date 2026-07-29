"""Grafos LangGraph dos 6 módulos do workflow jurídico (CLAUDE.md, seção 14).

Cada módulo é um StateGraph independente que opera sobre CaseState
(orchestrator/state.py). Só `intake.py` existe por enquanto — os demais
(evidence, research, strategy, drafting, review) dependem de nós que chamam
modelos de IA reais e serão adicionados quando esses módulos forem
implementados.
"""
