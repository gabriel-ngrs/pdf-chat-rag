const STORAGE_KEY = 'talkdoc:session-id'

/**
 * Gera um identificador aleatório.
 *
 * `crypto.randomUUID` só existe em contexto seguro; servido por IP na rede
 * local ele some, e sem o fallback o app quebraria no primeiro acesso.
 */
function randomId(): string {
  if (typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}

/**
 * Identidade da sessão, persistida no navegador e enviada em `X-Session-Id`.
 *
 * Serve para agrupar os documentos de um mesmo navegador — em especial para a
 * deduplicação por hash do backend. **Não é fronteira de segurança:** o valor é
 * escolhido pelo cliente e o servidor não o usa para autorizar nada.
 */
export function getSessionId(): string {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored) {
    return stored
  }
  const created = randomId()
  localStorage.setItem(STORAGE_KEY, created)
  return created
}
