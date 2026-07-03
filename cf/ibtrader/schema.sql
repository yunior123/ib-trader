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
  PRIMARY KEY (sym, ts)
);

-- Perfil por strike de la ultima instantanea (solo los que pesan: top por |gex|).
CREATE TABLE IF NOT EXISTS perfil (
  sym TEXT NOT NULL, ts INTEGER NOT NULL, strike REAL NOT NULL,
  call_oi REAL, put_oi REAL, call_vol REAL, put_vol REAL, gex REAL,
  PRIMARY KEY (sym, ts, strike)
);

-- Flujo de opciones de LSE: prima y griegas REALES, no reconstruidas.
CREATE TABLE IF NOT EXISTS flujo (
  id INTEGER PRIMARY KEY,           -- el id del vault: evita duplicar en cada vuelta
  ts TEXT NOT NULL, underlying TEXT NOT NULL, ticker TEXT NOT NULL,
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
