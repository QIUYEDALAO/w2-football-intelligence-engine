-- Read-only production schema capture 2026-09-30T19:52Z. No data/credentials.
-- Alembic=0076, known pre-0086 ORM ledger shape with unique slot INDEX.
CREATE TABLE public.ah_ou_decision_ledger (
    decision_id character varying(64) NOT NULL,
    fixture_id character varying(128) NOT NULL,
    market character varying(32) NOT NULL,
    decision_at timestamp with time zone NOT NULL,
    model_version character varying(128) NOT NULL,
    calibration_version character varying(128) NOT NULL,
    input_hash character varying(64) NOT NULL,
    full_distribution json NOT NULL,
    quote_identity_hash character varying(64) NOT NULL,
    source_capture_sha256 character varying(64) NOT NULL,
    capture_id character varying(64) NOT NULL,
    source_id character varying(255) NOT NULL,
    home_team_id character varying(128) NOT NULL,
    away_team_id character varying(128) NOT NULL,
    selected boolean NOT NULL,
    direction character varying(16),
    score character varying(64) NOT NULL,
    skip_reason character varying(255),
    created_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public.ah_ou_decision_ledger
    ADD CONSTRAINT ah_ou_decision_ledger_pkey PRIMARY KEY (decision_id);

CREATE INDEX ix_ah_ou_decision_ledger_capture ON public.ah_ou_decision_ledger USING btree (capture_id);

CREATE INDEX ix_ah_ou_decision_ledger_fixture ON public.ah_ou_decision_ledger USING btree (fixture_id, decision_at);

CREATE UNIQUE INDEX uq_ah_ou_decision_ledger_slot ON public.ah_ou_decision_ledger USING btree (fixture_id, market, decision_at);
