-- Migration 013: Market Prices and Technical Analysis State (Milestone 6)

CREATE TABLE IF NOT EXISTS market_prices (
  ticker text NOT NULL,
  dt     date NOT NULL,
  o      numeric,
  h      numeric,
  l      numeric,
  c      numeric,
  v      bigint,
  PRIMARY KEY (ticker, dt)
);

CREATE INDEX IF NOT EXISTS ix_market_prices_dt ON market_prices(dt);

CREATE TABLE IF NOT EXISTS technical_state (
  ticker             text PRIMARY KEY,
  as_of              date NOT NULL,
  sma20              numeric,
  sma50              numeric,
  sma200             numeric,
  rsi14              numeric,
  macd               numeric,
  macd_signal        numeric,
  bb_upper           numeric,
  bb_lower           numeric,
  atr14              numeric,
  vol_avg20          numeric,
  dist_52wk_high_pct numeric,
  dist_52wk_low_pct  numeric,
  trend              text,
  momentum           text,
  volatility         text,
  volume_regime      text,
  regime_label       text,
  stale_as_of        date
);

CREATE TABLE IF NOT EXISTS technical_state_history (
  ticker       text NOT NULL,
  as_of        date NOT NULL,
  snapshot     jsonb NOT NULL,
  PRIMARY KEY (ticker, as_of)
);
