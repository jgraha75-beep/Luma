export type FavoriteItem = {
  id: string
  sort_order: number
  food_name: string
  brand: string | null
  quantity_g: number
  nutrients: Record<string, number>
  nutrition_basis?: 'per_100g' | 'per_serving'
  serving_count?: number | null
  nutrients_per_serving?: Record<string, number> | null
  nutrient_source?: NutrientSource
  source_id?: string | null
}

export type Favorite = {
  id: string
  name: string
  created_at: string
  log_count?: number
  items: FavoriteItem[]
  tags?: string[]
}

import type { Nutrients } from '../../lib/nutrients'

export type DraftItem = {
  name: string
  brand?: string
  quantity: number
  unit: string
  estimated_weight_g: number
  // Original estimate captured when the item entered the draft, used to anchor
  // the relative portion multipliers (½×/1×/2×) so they don't drift as the
  // weight is edited.
  base_weight_g?: number
  nutrients: Nutrients
  // Tracks which food DB record this item came from (set for barcode, search,
  // and re-adds from Recent; absent for fresh photo extractions).
  food_id?: string
  // Provider-native identifier for sources that are not backed by the local
  // foods table (for example Tabecal's Japanese menu records).
  source_id?: string
  // Origin of the item so the backend can decide whether to auto-persist it.
  source?: 'barcode' | 'photo' | 'search' | 'voice' | 'plan' | 'manual'
  // Where the nutrient values came from after server-side resolution. DB-sourced
  // values are trustworthy; "estimate" means the LLM's own numbers were kept.
  nutrient_source?: 'reference' | 'usda' | 'user' | 'off' | 'tabecal' | 'estimate'
  // Japanese restaurant items are published per menu serving rather than per
  // 100g. Keep that basis explicit so gram edits never rescale them as if they
  // were weighed foods.
  nutrition_basis?: 'per_100g' | 'per_serving'
  nutrients_per_serving?: Record<string, number>
  serving_count?: number
}

export type NutrientSource = NonNullable<DraftItem['nutrient_source']>

// Map a picked food's origin to the provenance tag carried on a draft item, so
// a food chosen from the DB (search/barcode/replace) shows the right badge.
export function nutrientSourceForFood(source?: string, brand?: string): NutrientSource | undefined {
  if (brand === 'USDA Reference') return 'reference'
  if (source === 'usda') return 'usda'
  if (source === 'off') return 'off'
  if (source === 'tabecal') return 'tabecal'
  if (source === 'user') return 'user'
  return undefined
}
