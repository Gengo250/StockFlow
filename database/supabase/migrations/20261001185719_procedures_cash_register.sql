-- ==========================================
-- SOURCE: procedures/cash_register.sql
-- ==========================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE OR REPLACE PROCEDURE validate_login (
  v_name VARCHAR,
  pass VARCHAR,
  OUT is_valid BOOLEAN
)

LANGUAGE plpgsql
AS $$
DECLARE
  saved_hash VARCHAR;

BEGIN
  SELECT password into saved_hash
  FROM access_register
  WHERE v_name = name;

  IF saved_hash IS NOT NULL AND saved_hash = crypt(pass, saved_hash) THEN
    is_valid := TRUE;

  ELSE
    is_valid := FALSE;

  END IF;
END;
$$;
