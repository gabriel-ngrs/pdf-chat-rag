import { describe, expect, it } from 'vitest'

import { ERROR_CODES, describeError } from '@/lib/errors'

/** Os cinco códigos que a §4.3 da spec fixa como contrato entre os dois tracks. */
const CODIGOS_DA_SPEC = [
  'arquivo_grande',
  'arquivo_invalido',
  'nao_encontrado',
  'limite_de_uso',
  'erro_interno',
]

describe('describeError', () => {
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
      expect(description.severity).toBe('error')
    }
  })

  it('não repete a mesma frase para códigos diferentes', () => {
    const titles = ERROR_CODES.map((code) => describeError(code).title)
    expect(new Set(titles).size).toBe(ERROR_CODES.length)
  })

  it('cai no erro interno quando o servidor manda um código que a UI não conhece', () => {
    expect(describeError('codigo_que_nao_existe')).toEqual(describeError('erro_interno'))
  })
})
