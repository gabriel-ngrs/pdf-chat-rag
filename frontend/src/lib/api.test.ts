import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, fetchConfig, fetchDocument } from '@/lib/api'

function stubLocalStorage() {
  const store = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
    clear: () => store.clear(),
  })
}

function respondWith(body: string, init: ResponseInit) {
  const fetchMock = vi.fn((_input: RequestInfo | URL, requestInit?: RequestInit) => {
    void requestInit
    return Promise.resolve(new Response(body, init))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('cliente HTTP', () => {
  beforeEach(() => {
    stubLocalStorage()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('devolve o corpo quando o servidor responde com sucesso', async () => {
    respondWith(JSON.stringify({ max_upload_mb: 25, max_pdf_pages: 20, max_extracted_chars: 60000 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })

    await expect(fetchConfig()).resolves.toEqual({
      max_upload_mb: 25,
      max_pdf_pages: 20,
      max_extracted_chars: 60000,
    })
  })

  it('envia o identificador de sessão em toda requisição', async () => {
    const fetchMock = respondWith('{}', { status: 200 })

    await fetchConfig()

    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Record<string, string>
    expect(headers['X-Session-Id']).toMatch(/.+/)
  })

  it('traduz o envelope de erro do servidor para o código correspondente', async () => {
    respondWith(JSON.stringify({ code: 'nao_encontrado', message: 'Documento não existe.' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    })

    await expect(fetchDocument('abc')).rejects.toMatchObject({
      code: 'nao_encontrado',
      status: 404,
    })
  })

  // O nginx ou um proxy mal configurado responde HTML; `response.json()` em cima
  // disso quebraria de forma opaca e a interface ficaria sem código para usar.
  it('não quebra quando a resposta de erro não é JSON', async () => {
    respondWith('<html><body>413 Request Entity Too Large</body></html>', {
      status: 413,
      headers: { 'Content-Type': 'text/html' },
    })

    const failure = await fetchConfig().catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(ApiError)
    expect((failure as ApiError).code).toBe('erro_interno')
    expect((failure as ApiError).status).toBe(413)
  })

  it('não quebra quando a resposta de sucesso não é JSON', async () => {
    respondWith('<html>índice do nginx</html>', {
      status: 200,
      headers: { 'Content-Type': 'text/html' },
    })

    await expect(fetchConfig()).rejects.toMatchObject({ code: 'erro_interno' })
  })

  it('traduz falha de rede em rede_indisponivel, sem status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )

    await expect(fetchConfig()).rejects.toMatchObject({
      code: 'rede_indisponivel',
      status: null,
    })
  })
})
