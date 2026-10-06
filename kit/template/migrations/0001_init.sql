-- 0001: households, members, entries, activity -- every table tenant-scoped by RLS.
--
-- Every policy keys on current_setting('app.tenant_id', true). Unset, it is NULL;
-- set to '', nullif makes it NULL; either way no row matches.
-- tests/test_rls_unbound.py reads every public table as the app role with the
-- tenant unset and set to '' and requires 0 rows, and fails a table without RLS.

CREATE TABLE households (
    id   text PRIMARY KEY CHECK (id ~ '^[a-z0-9_]{1,64}$'),
    name text NOT NULL
);

CREATE TABLE members (
    id           text PRIMARY KEY CHECK (id ~ '^[a-z0-9_]{1,64}$'),
    household_id text NOT NULL REFERENCES households (id) ON DELETE CASCADE,
    display_name text NOT NULL,
    tz           text NOT NULL,
    token        text NOT NULL UNIQUE
);

CREATE TABLE entries (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id text NOT NULL REFERENCES households (id) ON DELETE CASCADE,
    member_id    text NOT NULL REFERENCES members (id) ON DELETE CASCADE,
    amount_cents bigint NOT NULL,
    occurred_on  date NOT NULL,          -- the member's local date when recorded
    recorded_at  timestamptz NOT NULL,   -- from the clock seam, never now()
    note         text NOT NULL DEFAULT ''
);
CREATE INDEX entries_household_day ON entries (household_id, occurred_on);
CREATE INDEX entries_member_day ON entries (member_id, occurred_on);

CREATE TABLE activity (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id text NOT NULL REFERENCES households (id) ON DELETE CASCADE,
    member_id    text REFERENCES members (id) ON DELETE CASCADE,
    kind         text NOT NULL,
    at           timestamptz NOT NULL
);

ALTER TABLE households ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant ON households
    USING (id = nullif(current_setting('app.tenant_id', true), ''))
    WITH CHECK (id = nullif(current_setting('app.tenant_id', true), ''));

ALTER TABLE members ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant ON members
    USING (household_id = nullif(current_setting('app.tenant_id', true), ''))
    WITH CHECK (household_id = nullif(current_setting('app.tenant_id', true), ''));

ALTER TABLE entries ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant ON entries
    USING (household_id = nullif(current_setting('app.tenant_id', true), ''))
    WITH CHECK (household_id = nullif(current_setting('app.tenant_id', true), ''));

ALTER TABLE activity ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant ON activity
    USING (household_id = nullif(current_setting('app.tenant_id', true), ''))
    WITH CHECK (household_id = nullif(current_setting('app.tenant_id', true), ''));

-- Token -> member before any tenant is known. SECURITY DEFINER runs as the
-- owner, which RLS does not restrict; it returns one member or nothing.
CREATE FUNCTION member_by_token(p_token text)
RETURNS TABLE (id text, household_id text, display_name text, tz text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT m.id, m.household_id, m.display_name, m.tz
    FROM public.members m
    WHERE m.token = p_token
$$;

-- Maintenance across every household (the prune_activity schedule).
CREATE FUNCTION prune_activity(p_before timestamptz)
RETURNS bigint
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    WITH gone AS (DELETE FROM public.activity WHERE at < p_before RETURNING 1)
    SELECT count(*) FROM gone
$$;

REVOKE ALL ON FUNCTION member_by_token(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION prune_activity(timestamptz) FROM PUBLIC;

DO $grant$
DECLARE
    app_role text := current_setting('rails.app_role');
BEGIN
    EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', app_role);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', app_role);
    EXECUTE format('GRANT EXECUTE ON FUNCTION member_by_token(text), prune_activity(timestamptz) TO %I', app_role);
END
$grant$;
