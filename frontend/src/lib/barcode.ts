/** Barcode values accepted by the food lookup providers. */
const VALID_LENGTHS = new Set([8, 12, 13, 14])

/**
 * Normalize a scanner result before sending it to the API.
 *
 * Camera libraries can include whitespace or formatting characters in a
 * decoded value. Luma only supports numeric retail product identifiers, so
 * reject anything that cannot be a standard EAN/UPC value instead of making a
 * provider request that is guaranteed to fail.
 */
export function normalizeBarcode(raw: string): string | null {
  const digits = raw.replace(/\D/g, '')
  return VALID_LENGTHS.has(digits.length) ? digits : null
}
