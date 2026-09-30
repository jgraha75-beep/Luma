import { describe, expect, it } from 'vitest'
import { normalizeBarcode } from '../lib/barcode'

describe('normalizeBarcode', () => {
  it('keeps supported retail barcode digits and removes formatting', () => {
    expect(normalizeBarcode('  0 28400-07056 6 ')).toBe('028400070566')
    expect(normalizeBarcode('5901234123457')).toBe('5901234123457')
  })

  it('rejects values that cannot be sent to the food lookup providers', () => {
    expect(normalizeBarcode('')).toBeNull()
    expect(normalizeBarcode('abc-123')).toBeNull()
    expect(normalizeBarcode('123456789')).toBeNull()
  })
})
