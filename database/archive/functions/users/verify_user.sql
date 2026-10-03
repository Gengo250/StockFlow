
CREATE OR REPLACE FUNCTION public.fn_is_valid_pass_hash(p_hash text)
RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT p_hash IS NOT NULL AND left(p_hash, 1) = '$' AND length(p_hash) >= 20;
$$;