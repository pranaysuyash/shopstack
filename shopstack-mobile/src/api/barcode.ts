export interface BarcodeProduct {
  code: string;
  name: string;
  brand: string;
  category: string;
  quantity: string;
  imageUrl: string;
  nutriscore: string;
  nutritionPer100g: Record<string, number> | null;
}

export async function lookupBarcode(code: string): Promise<BarcodeProduct | null> {
  const url = `https://world.openfoodfacts.org/api/v2/product/${encodeURIComponent(code)}.json`;
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) return null;
  const json = await res.json();
  if (json.status !== 1 || !json.product) return null;
  const p = json.product;
  const nutriments: Record<string, number> | null = p.nutriments ?? null;
  return {
    code,
    name: p.product_name || p.product_name_en || `Product ${code}`,
    brand: p.brands || '',
    category: p.categories?.split(',')?.[0]?.trim() || '',
    quantity: p.quantity || '',
    imageUrl: p.image_url || p.image_front_small_url || '',
    nutriscore: p.nutriscore_grade || '',
    nutritionPer100g: nutriments,
  };
}
