-- Safe, repeatable catalog seed from the existing Zarma frontend fixture.
-- This migration never deletes rows and never overwrites existing inventory.

insert into public.categories (name, slug, active) values
  ('Shirts', 'shirts', true),
  ('Trousers', 'trousers', true),
  ('Shoes', 'shoes', true),
  ('Accessories', 'accessories', true)
on conflict (slug) do update set name = excluded.name, active = true;

insert into public.products (category_id, name, slug, description, price_pkr, active)
select c.id, v.name, v.slug, v.description, v.price_pkr, true
from (values
  ('Shirts', 'Noir Oxford Shirt', 'noir-oxford-shirt', 'A clean black oxford with a soft, structured hand.', 4890),
  ('Trousers', 'Sand Pleated Trousers', 'sand-pleated-trousers', 'A relaxed straight leg that balances darker shirts.', 6250),
  ('Shoes', 'Cedar Leather Loafers', 'cedar-leather-loafers', 'Polished leather, easy enough for long wedding evenings.', 8900),
  ('Accessories', 'Bridle Leather Belt', 'bridle-leather-belt', 'A quiet finishing detail in full-grain leather.', 1950),
  ('Accessories', 'Field Watch 38', 'field-watch-38', 'A warm steel watch with a simple, legible face.', 12900),
  ('Shirts', 'Ivory Linen Camp Shirt', 'ivory-linen-camp-shirt', 'Lightweight linen with a relaxed collar for summer.', 5350)
) as v(category_name, name, slug, description, price_pkr)
join public.categories c on c.name = v.category_name
on conflict (slug) do update set
  category_id = excluded.category_id,
  name = excluded.name,
  description = excluded.description,
  price_pkr = excluded.price_pkr,
  active = true;

insert into public.product_variants (product_id, sku, size, color, price_pkr)
select p.id, v.sku, v.size, v.color, v.price_pkr
from (values
  ('noir-oxford-shirt', 'ZM-NOIR-S', 'S', 'Black', 4890),
  ('noir-oxford-shirt', 'ZM-NOIR-M', 'M', 'Black', 4890),
  ('noir-oxford-shirt', 'ZM-NOIR-L', 'L', 'Black', 4890),
  ('noir-oxford-shirt', 'ZM-NOIR-XL', 'XL', 'Black', 4890),
  ('sand-pleated-trousers', 'ZM-SAND-30', '30', 'Sand', 6250),
  ('sand-pleated-trousers', 'ZM-SAND-32', '32', 'Sand', 6250),
  ('sand-pleated-trousers', 'ZM-SAND-34', '34', 'Sand', 6250),
  ('sand-pleated-trousers', 'ZM-SAND-36', '36', 'Sand', 6250),
  ('cedar-leather-loafers', 'ZM-CEDAR-40', '40', 'Brown', 8900),
  ('cedar-leather-loafers', 'ZM-CEDAR-41', '41', 'Brown', 8900),
  ('cedar-leather-loafers', 'ZM-CEDAR-42', '42', 'Brown', 8900),
  ('cedar-leather-loafers', 'ZM-CEDAR-43', '43', 'Brown', 8900),
  ('bridle-leather-belt', 'ZM-BRIDLE-32', '32', 'Brown', 1950),
  ('bridle-leather-belt', 'ZM-BRIDLE-34', '34', 'Brown', 1950),
  ('bridle-leather-belt', 'ZM-BRIDLE-36', '36', 'Brown', 1950),
  ('field-watch-38', 'ZM-FIELD-ONE', 'One size', 'Steel', 12900),
  ('ivory-linen-camp-shirt', 'ZM-IVORY-S', 'S', 'Ivory', 5350),
  ('ivory-linen-camp-shirt', 'ZM-IVORY-M', 'M', 'Ivory', 5350),
  ('ivory-linen-camp-shirt', 'ZM-IVORY-L', 'L', 'Ivory', 5350),
  ('ivory-linen-camp-shirt', 'ZM-IVORY-XL', 'XL', 'Ivory', 5350)
) as v(product_slug, sku, size, color, price_pkr)
join public.products p on p.slug = v.product_slug
on conflict (sku) do update set
  product_id = excluded.product_id,
  size = excluded.size,
  color = excluded.color,
  price_pkr = excluded.price_pkr;

-- Add starter inventory only when a variant has no inventory row. Existing stock is preserved.
insert into public.inventory (variant_id, quantity, reserved_quantity)
select v.id, 10, 0
from public.product_variants v
where v.sku like 'ZM-%'
  and not exists (select 1 from public.inventory i where i.variant_id = v.id);
