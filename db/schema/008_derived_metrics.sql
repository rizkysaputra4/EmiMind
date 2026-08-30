CREATE TABLE peer_groups (
  id          text PRIMARY KEY,
  name        text NOT NULL,
  tickers     text[] NOT NULL,
  sector      text,
  sub_sector  text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE derived_metrics (
  id              bigserial PRIMARY KEY,
  ticker          text NOT NULL,
  fiscal_period   text NOT NULL,
  metric_id       text NOT NULL,
  value_numeric   numeric(24,6),
  unit            text,
  inputs          jsonb,
  peer_group_id   text REFERENCES peer_groups(id),
  computed_at     timestamptz NOT NULL DEFAULT now(),
  recipe_version  text NOT NULL
);

CREATE UNIQUE INDEX ux_derived_metrics_key
  ON derived_metrics (ticker, fiscal_period, metric_id, coalesce(peer_group_id,''));

CREATE INDEX ix_derived_metrics_metric_period_val
  ON derived_metrics (metric_id, fiscal_period, value_numeric);

CREATE INDEX ix_derived_metrics_ticker_metric
  ON derived_metrics (ticker, metric_id, fiscal_period);
