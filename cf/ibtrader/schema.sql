-- Mapa por simbolo: una fila por instantanea. Nada se sobrescribe: el historico ES el producto.
CREATE TABLE IF NOT EXISTS niveles (
  sym TEXT NOT NULL,
  ts INTEGER NOT NULL,              -- epoch de la instantanea
  fuente_ts TEXT,                   -- last_trade_time que declara CBOE (no el nuestro)
  spot REAL NOT NULL,
  call_wall REAL, call_wall_oi REAL,
  put_wall REAL, put_wall_oi REAL,
  flip REAL,                        -- strike donde el GEX acumulado cruza cero; NULL si no cruza
  max_pain REAL,
  gex_total REAL,                   -- $ por punto de movimiento del subyacente
  contratos INTEGER, strikes INTEGER,
  -- Anadidas por ALTER en produccion; el fichero se habia quedado atras y un despliegue
  -- limpio no reproducia la tabla (comprobado contra sqlite_master el 2026-08-24).
  flip_raices TEXT,                 -- todas las raices del GEX acumulado, no solo la publicada
  gross_gex REAL, strike_span_pct REAL,
  net_vex REAL, gross_vex REAL, net_charm REAL, gross_charm REAL,
  pressure REAL, em REAL, dte INTEGER, exp TEXT,
  greeks_ok_pct REAL,               -- fraccion de contratos con IV legible; 0 => vex/charm NULL
  dex_bruto REAL,
  muros_dte INTEGER,                -- horizonte en dias del OI de los muros; NULL = cadena entera
  muros_banda REAL,                 -- +/- $ alrededor del spot dentro de los que se busco el muro
  PRIMARY KEY (sym, ts)
);

-- Perfil por strike de la ultima instantanea (solo los que pesan: top por |gex|).
CREATE TABLE IF NOT EXISTS perfil (
  sym TEXT NOT NULL, ts INTEGER NOT NULL, strike REAL NOT NULL,
  call_oi REAL, put_oi REAL, call_vol REAL, put_vol REAL, gex REAL, vex REAL, charm REAL,
  PRIMARY KEY (sym, ts, strike)
);

-- Flujo de opciones de LSE: prima y griegas REALES, no reconstruidas.
CREATE TABLE IF NOT EXISTS flujo (
  id INTEGER PRIMARY KEY,           -- el id del vault: evita duplicar en cada vuelta
  ts TEXT NOT NULL,                 -- UTC naive de LSE; /api/flujo añade source_ts_epoch/source_ts_utc
  underlying TEXT NOT NULL, ticker TEXT NOT NULL,
  strike REAL, expiry TEXT, tipo TEXT, dte INTEGER,
  last_price REAL, volume REAL, premium REAL, underlying_price REAL,
  iv REAL, delta REAL, gamma REAL
);
CREATE INDEX IF NOT EXISTS idx_flujo_ts ON flujo(ts DESC);
CREATE INDEX IF NOT EXISTS idx_flujo_prima ON flujo(premium DESC);

-- Barras 1m de LSE.
CREATE TABLE IF NOT EXISTS barras (
  sym TEXT NOT NULL, ts TEXT NOT NULL,
  o REAL, h REAL, l REAL, c REAL, v REAL,
  PRIMARY KEY (sym, ts)
);

-- Bitacora: si una vuelta falla hay que poder verlo, no adivinarlo.
CREATE TABLE IF NOT EXISTS vueltas (
  ts INTEGER NOT NULL, tarea TEXT NOT NULL, ok INTEGER NOT NULL,
  ms INTEGER, detalle TEXT
);
CREATE INDEX IF NOT EXISTS idx_vueltas_ts ON vueltas(ts DESC);

-- Ultima cotacion viva por simbolo (barrido rotativo /api/quotes, Finnhub free tier).
-- Compartida entre isolates: la rotacion lee de aqui para saber a quien refrescar.
CREATE TABLE IF NOT EXISTS quotes (
  sym   TEXT PRIMARY KEY,
  price REAL,
  prev  REAL,
  ts    INTEGER,              -- epoch s del quote segun la fuente
  at    INTEGER               -- epoch ms de cuando se tomó
);
