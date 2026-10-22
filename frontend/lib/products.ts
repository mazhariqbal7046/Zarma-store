export type Product = {
  id: string;
  variantId?: string;
  name: string;
  category: "Shirts" | "Trousers" | "Shoes" | "Accessories" | "Baby";
  price: number;
  color: string;
  sizes: string[];
  image: string;
  tone: string;
  stock?: number;
  seller?: string;
};

export const products: Product[] = [
  { id: "shirt-01", name: "Noir Oxford Shirt", category: "Shirts", price: 4890, color: "Black", sizes: ["S", "M", "L", "XL"], image: "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?auto=format&fit=crop&w=900&q=85", tone: "A clean black oxford with a soft, structured hand." },
  { id: "trouser-01", name: "Sand Pleated Trousers", category: "Trousers", price: 6250, color: "Sand", sizes: ["30", "32", "34", "36"], image: "https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?auto=format&fit=crop&w=900&q=85", tone: "A relaxed straight leg that balances darker shirts." },
  { id: "shoe-01", name: "Cedar Leather Loafers", category: "Shoes", price: 8900, color: "Brown", sizes: ["40", "41", "42", "43"], image: "https://images.unsplash.com/photo-1614252369475-531eba835eb1?auto=format&fit=crop&w=900&q=85", tone: "Polished leather, easy enough for long wedding evenings." },
  { id: "belt-01", name: "Bridle Leather Belt", category: "Accessories", price: 1950, color: "Brown", sizes: ["32", "34", "36"], image: "https://images.unsplash.com/photo-1624222247344-550fb60583dc?auto=format&fit=crop&w=900&q=85", tone: "A quiet finishing detail in full-grain leather." },
  { id: "watch-01", name: "Field Watch 38", category: "Accessories", price: 12900, color: "Steel", sizes: ["One size"], image: "https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=900&q=85", tone: "A warm steel watch with a simple, legible face." },
  { id: "shirt-02", name: "Ivory Linen Camp Shirt", category: "Shirts", price: 5350, color: "Ivory", sizes: ["S", "M", "L", "XL"], image: "https://images.unsplash.com/photo-1603252110481-7ba873bf42ab?auto=format&fit=crop&w=900&q=85", tone: "Lightweight linen with a relaxed collar for summer." },
  { id: "demo-watch-01", name: "Noor Minimal Watch", category: "Accessories", price: 7200, color: "Silver", sizes: ["One size"], image: "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=900&q=85", tone: "A clean everyday watch from Demo Seller.", seller: "Demo Seller" },
  { id: "demo-baby-01", name: "Little Cloud Cotton Set", category: "Baby", price: 2850, color: "Sky blue", sizes: ["0-3M", "3-6M", "6-12M"], image: "https://images.unsplash.com/photo-1519689680058-324335c77eba?auto=format&fit=crop&w=900&q=85", tone: "Soft cotton essentials for little ones.", seller: "Demo Seller" },
  { id: "demo-shoe-01", name: "Cocoa Street Sneakers", category: "Shoes", price: 6450, color: "Cocoa", sizes: ["39", "40", "41", "42"], image: "https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=900&q=85", tone: "Comfort-first sneakers from Demo Seller.", seller: "Demo Seller" }
];

export function searchProducts(query: string) {
  const q = query.toLowerCase();
  return products.filter((product) => `${product.name} ${product.category} ${product.color}`.toLowerCase().includes(q) || (q.includes("shirt") && product.category === "Shirts"));
}

export function productFromBackend(value: { id: string; name: string; description?: string | null; price_pkr?: number; product_images?: Array<Record<string, unknown>>; product_variants?: Array<{ id: string; size?: string; stock?: number; quantity?: number; price_pkr?: number }> }): Product {
  const variant = value.product_variants?.find((item) => (item.stock ?? item.quantity ?? 0) > 0) ?? value.product_variants?.[0];
  const image = value.product_images?.find((item) => typeof item.url === "string" || typeof item.public_url === "string");
  const imageUrl = image && (typeof image.url === "string" ? image.url : typeof image.public_url === "string" ? image.public_url : undefined);
  return {
    id: value.id,
    variantId: variant?.id,
    name: value.name,
    category: "Accessories",
    price: variant?.price_pkr ?? value.price_pkr ?? 0,
    color: "",
    sizes: value.product_variants?.map((item) => item.size).filter((size): size is string => Boolean(size)) ?? [],
    image: imageUrl ?? "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?auto=format&fit=crop&w=900&q=85",
    tone: value.description ?? "Available from the Zarma Store catalog.",
    stock: value.product_variants?.reduce((total, item) => total + (item.stock ?? item.quantity ?? 0), 0),
  };
}
