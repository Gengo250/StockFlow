CREATE OR REPLACE FUNCTION fn_edit_product_stock(
  p_user UUID,
  p_product_barcode VARCHAR,
  p_new_qtt INTEGER
)
RETURNS VOID


LANGUAGE plpgsql
AS $$
DECLARE
  v_is_permitted BOOLEAN;
  v_old_stock INTEGER;
  v_new_stock INTEGER;


BEGIN 

  IF p_new_qtt < 0 THEN
    RAISE EXCEPTION 'PRODUCT CANT HAVE NEGATIVE QUANTITY';
  END IF;

  SELECT EXISTS (
    SELECT 1
    FROM company_users
    WHERE id = p_user
    AND (role = 'STOCK'OR role = 'ADMIN')
  ) INTO v_is_permitted;

  IF NOT v_is_permitted THEN
    RAISE EXCEPTION 'ACCESS DENIED, USER WITH NO PERMISSIONS TO ALTER STOCK';
  END IF;

  SELECT stock INTO v_old_stock
  FROM products
  WHERE barcode = p_product_barcode;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'PRODUCT NOT FOUND';
  END IF;

  v_new_stock := v_old_stock + p_new_qtt;

  UPDATE products
  SET stock = v_new_stock,
      updated_on = NOW(),
      last_updated_by = p_user
  WHERE barcode = p_product_barcode;

END;
$$;
