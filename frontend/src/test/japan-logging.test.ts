import { describe, expect, it } from 'vitest'
import { handleMockApiRequest } from '../lib/mock-api'

describe('Japan menu logging contract', () => {
  it('keeps mock menu results explicitly per serving', async () => {
    const result = await handleMockApiRequest('/foods/japan/search?q=牛丼', { method: 'GET' }) as Array<Record<string, unknown>>
    expect(result).toHaveLength(1)
    expect(result[0].source).toBe('tabecal')
    expect(result[0].nutrition_basis).toBe('per_serving')
    expect((result[0].nutrients as Record<string, number>).calories).toBe(635)
  })
})
