-- ==========================================
-- SOURCE: tables/cash_register.sql
-- ==========================================

CREATE TABLE access_register (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  name TEXT NOT NULL,
  pass_hash TEXT NOT NULL
  
);

CREATE TABLE register (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  session_id UUID REFERENCES access_register(id) ON DELETE SET NULL,
  change NUMERIC(10,2),

  logged_on TIMESTAMPTZ DEFAULT NOW()
);