-- ==========================================
-- SOURCE: procedures/products.sql
-- ==========================================

CREATE OR REPLACE FUNCTION create_categories (
  p_name TEXT
)
RETURNS UUID 
LANGUAGE plpgsql
AS $$
DECLARE
  v_new_id UUID;
BEGIN
  IF EXISTS (SELECT 1 FROM categories WHERE name = p_name) THEN
    RAISE EXCEPTION 'Category already exists';
  END IF;

  INSERT INTO categories (
    name
  )
  VALUES (
    p_name
  )
  RETURNING id INTO v_new_id;

  RETURN v_new_id;
END;
$$;
CREATE OR REPLACE FUNCTION create_products (
  p_barcode TEXT,
  p_name TEXT,
  p_sell_price NUMERIC (10, 2),
  p_buy_price NUMERIC (10, 2) DEFAULT NULL,
  p_unit unit_enum DEFAULT 'UN',
  p_stock INTEGER DEFAULT 0,
  p_item_category TEXT DEFAULT NULL
)
RETURNS UUID 
LANGUAGE plpgsql
AS $$
DECLARE
  v_new_id UUID;
  v_category_id UUID;
BEGIN
  IF p_item_category IS NOT NULL THEN 
    SELECT id INTO v_category_id FROM categories WHERE name = p_item_category;
    
    IF v_category_id IS NULL THEN
      RAISE EXCEPTION 'Item category doesnt exist';
  
    END IF;
  END IF;

  INSERT INTO products (
    barcode, 
    name, 
    buy_price, 
    sell_price, 
    unit,
    stock,
    item_category
  )
  VALUES (
    p_barcode,
    p_name,
    p_buy_price,
    p_sell_price,
    p_unit,
    p_stock,
    v_category_id
  )
  RETURNING id into v_new_id;

  RETURN v_new_id;
END;
$$;
