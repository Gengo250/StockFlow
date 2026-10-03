-- Login do caixa. Independente do resto.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE PROCEDURE pr_validate_login (
  v_name VARCHAR,
  pass VARCHAR,
  OUT is_valid BOOLEAN
)

LANGUAGE plpgsql
SET search_path = public, extensions
AS $$
DECLARE
  saved_hash VARCHAR;

BEGIN
  BEGIN
    -- STRICT: access_register.name é UNIQUE, então mais de uma linha aqui
    -- significa que a restrição caiu. Falhar alto é melhor que autenticar
    -- contra um hash arbitrário.
    SELECT pass_hash INTO STRICT saved_hash
    FROM access_register
    WHERE name = v_name;

  EXCEPTION
    -- Nome inexistente é login inválido, não erro.
    WHEN NO_DATA_FOUND THEN
      is_valid := FALSE;
      RETURN;
  END;

  -- pass NULL faz crypt() devolver NULL; o ELSE cobre esse caso.
  IF saved_hash = crypt(pass, saved_hash) THEN
    is_valid := TRUE;

  ELSE
    is_valid := FALSE;

  END IF;
END;
$$;
