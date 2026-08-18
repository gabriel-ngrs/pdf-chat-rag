import { describe, expect, it } from 'vitest'

import { ERROR_CODES, describeError } from '@/lib/errors'
import type { ErrorCode, NoticeSeverity } from '@/lib/errors'

/** Os cinco códigos que a §4.3 da spec fixa como contrato entre os dois tracks. */
const CODIGOS_DA_SPEC = [
  'arquivo_grande',
  'arquivo_invalido',
  'entrada_invalida',
  'nao_encontrado',
  'limite_de_uso',
  'erro_interno',
]

/**
 * A severidade que cada código deve ter, escrita à mão.
 *
 * Tabela explícita, e não "está entre as três severidades": o despacho de
 * avisos escolhe canal e duração por este campo, então um código marcado
 * `success` por engano viraria um toast verde para uma falha — e uma asserção
 * que aceita qualquer uma das três deixaria isso passar.
 */
const SEVERIDADE_ESPERADA: Record<ErrorCode, NoticeSeverity> = {
  arquivo_grande: 'error',
  arquivo_invalido: 'error',
  entrada_invalida: 'error',
  nao_encontrado: 'error',
  limite_de_uso: 'error',
  erro_interno: 'error',
  rede_indisponivel: 'error',
  provedor: 'error',
  documento_nao_pronto: 'info',
}

describe('describeError', () => {
  it('não promete que esperar um minuto resolve o limite de uso', () => {
    // BUG-004: a cota que estoura no plano gratuito é de 20 requisições por
    // dia, por modelo. Mandar esperar um minuto faz a pessoa tentar de novo,
    // falhar de novo, e concluir que o app está quebrado.
    const { action } = describeError('limite_de_uso')

    expect(action).toContain('diário')
    expect(action).not.toMatch(/cerca de um minuto/)
  })

  it('explica que uma pergunta longa precisa ser encurtada', () => {
    const description = describeError('entrada_invalida')

    expect(description.title).toMatch(/pergunta/i)
    expect(description.action).toMatch(/2\.000 caracteres/)
  })

  it('descreve todos os códigos do envelope da spec', () => {
    for (const code of CODIGOS_DA_SPEC) {
      expect(ERROR_CODES).toContain(code)
    }
  })

  it('dá título, mensagem e ação em pt-BR para cada código conhecido', () => {
    for (const code of ERROR_CODES) {
      const description = describeError(code)
      expect(description.title.length).toBeGreaterThan(0)
      expect(description.message.length).toBeGreaterThan(0)
      expect(description.action.length).toBeGreaterThan(0)
    }
  })

  it('dá a cada código a severidade que o despacho de avisos espera', () => {
    // Nem todo código é erro: `documento_nao_pronto` é estado transitório do
    // documento — sai como aviso neutro, não como falha de quem perguntou.
    for (const code of ERROR_CODES) {
      expect(describeError(code).severity).toBe(SEVERIDADE_ESPERADA[code])
    }
    // A tabela cobre o mapa inteiro: código novo sem severidade declarada aqui
    // reprova em vez de entrar sem ninguém decidir como ele aparece.
    expect(Object.keys(SEVERIDADE_ESPERADA).sort()).toEqual([...ERROR_CODES].sort())
  })

  it('não repete a mesma frase para códigos diferentes', () => {
    const titles = ERROR_CODES.map((code) => describeError(code).title)
    expect(new Set(titles).size).toBe(ERROR_CODES.length)
  })

  it('cai no erro interno quando o servidor manda um código que a UI não conhece', () => {
    expect(describeError('codigo_que_nao_existe')).toEqual(describeError('erro_interno'))
  })
})
