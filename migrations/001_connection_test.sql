-- Tabela usada apenas para validar a conexão do cliente desktop com o Supabase.
-- Executar no SQL Editor do painel do Supabase.

create table public.connection_test (
    id int8 primary key generated always as identity,
    message text
);

alter table public.connection_test enable row level security;

-- Sem esta policy a chave publishable (role anon) enxerga a tabela vazia,
-- mesmo que existam linhas.
create policy "leitura publica connection_test"
    on public.connection_test for select
    to anon
    using (true);
