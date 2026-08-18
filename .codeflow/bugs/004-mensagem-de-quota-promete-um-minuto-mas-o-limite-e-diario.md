---
id: BUG-004
titulo: "A mensagem de limite de uso promete 'espere um minuto', mas a cota que estoura é diária"
descoberto_em: 2026-08-17
descoberto_por: teste de ponta a ponta do owner (bloco 6 do roteiro)
severidade: média
fase_dona: B.4 (notices-persistence) e A.4 (chat-endpoint)
status: aberto
---

# BUG-004 — A orientação da mensagem de quota está errada

## Sintoma

Ao estourar a cota, a interface mostra:

> **Limite de uso atingido**
> O provedor de IA recusou mais requisições por enquanto.
> Espere cerca de um minuto e tente de novo.

O usuário espera um minuto, clica em "Tentar de novo" e falha de novo — porque a
cota que estourou **não era por minuto**.

## Causa raiz

A resposta crua do provedor, capturada no log:

```json
{
  "quotaId":     "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
  "quotaValue":  "20",
  "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
  "model":       "gemini-3.6-flash"
}
```

São **20 requisições por dia**, por modelo, no plano gratuito. O `429` também
traz `retryDelay: 58s`, que é a dica genérica da API — e foi provavelmente ela
que originou o texto. Para uma cota diária, o número não ajuda em nada.

O texto está em dois lugares:

- `backend/app/adapters/gemini.py:62` — `CHAT_QUOTA_MESSAGE`
- `frontend/src/lib/errors.ts:61` — o `action` do código `limite_de_uso`

## Por que importa para a entrega

O caminho técnico está **correto**: o `429` é detectado, mapeado para
`limite_de_uso`, sai como HTTP 429 antes do stream abrir, e a interface mostra
aviso com ação e preserva a pergunta digitada. Tudo isso é o AC-12 e passa.

O que falha é a orientação. Numa demonstração, o avaliador segue a instrução do
próprio produto, ela não funciona, e a conclusão é que o app está quebrado —
quando o comportamento está certo e só o conselho está errado.

## Correção sugerida

Trocar a ação por algo que cubra os dois casos, já que o adapter não distingue
qual das duas cotas estourou:

> "Pode ser o limite por minuto ou o limite diário do plano gratuito. Espere um
> pouco e tente de novo; se persistir, a cota do dia acabou."

Se quiser precisão, o `quotaId` vem no corpo do erro e permite distinguir — mas
isso é lógica nova no adapter, e a mensagem honesta acima resolve sem código
novo além do texto.

**Nota para a `B.5`:** o vídeo e a demonstração dependem dessa cota. Com 20
gerações por dia e por modelo, planeje a gravação — e considere trocar
`GEMINI_CHAT_MODEL` antes de gravar, porque cada modelo tem balde próprio.

## Encaminhamento

Rework da `B.4` (dona de `errors.ts`) para o texto da interface e da `A.4` (dona
de `gemini.py`) para o texto do backend, ou um `/bugfix` cobrindo os dois. **Não**
consertar dentro da `B.5`.
