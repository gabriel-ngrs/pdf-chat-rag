"""Backend do TalkDoc.

Três camadas, com dependências fluindo para dentro: `api/` → `adapters/` →
`core/`. A direção é verificada por `make arch`, não confiada à disciplina.
"""
