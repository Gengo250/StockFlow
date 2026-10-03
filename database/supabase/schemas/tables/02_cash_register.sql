-- Caixa. Independente das demais tabelas.

CREATE TABLE access_register (
  id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- UNIQUE: pr_validate_login resolve o hash por nome com SELECT ... INTO.
  -- Sem a restrição, dois cadastros homônimos deixam uma conta autenticar
  -- com a senha da outra.
  name      TEXT NOT NULL UNIQUE,
  pass_hash TEXT NOT NULL
);

CREATE TABLE register (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID REFERENCES access_register(id) ON DELETE SET NULL,
  change     NUMERIC(10,2),
  logged_on  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX register_session_id_idx ON register(session_id);
