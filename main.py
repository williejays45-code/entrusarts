
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="EnTrus Cloud Core - Flow Station")

# -------------------------------------------------------------------
# HTML Dashboard
# -------------------------------------------------------------------

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>EnTrus Flow Station</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    :root {
      --bg: #062318;
      --bg-alt: #0c3724;
      --card: #10402a;
      --accent: #f4c96a;
      --accent-soft: #f7dda0;
      --text-main: #f8f9f5;
      --text-soft: #b4c9b9;
      --border-soft: rgba(244, 201, 106, 0.25);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top, rgba(244,201,106,0.18) 0, transparent 55%),
        linear-gradient(135deg, #02130d 0%, var(--bg) 40%, #041810 100%);
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      align-items: stretch;
      justify-content: center;
      padding: 32px 16px;
    }

    .frame {
      width: 100%;
      max-width: 1120px;
      border-radius: 24px;
      border: 1px solid var(--border-soft);
      background:
        radial-gradient(circle at top left, rgba(244,201,106,0.18) 0, transparent 55%),
        linear-gradient(145deg, rgba(5,37,23,0.96), rgba(2,18,11,0.98));
      box-shadow:
        0 22px 60px rgba(0,0,0,0.65),
        0 0 0 1px rgba(1,11,7,0.6);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    .frame-header {
      padding: 20px 26px 16px;
      border-bottom: 1px solid rgba(244,201,106,0.15);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }

    .brand-block {
      display: flex;
      align-items: center;
      gap: 14px;
    }

    .brand-mark {
      width: 34px;
      height: 34px;
      border-radius: 999px;
      border: 1px solid rgba(244,201,106,0.6);
      background:
        radial-gradient(circle at 30% 0%, rgba(244,201,106,0.8) 0, transparent 55%),
        radial-gradient(circle at 70% 100%, rgba(53,249,157,0.25) 0, transparent 55%),
        #041a10;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      overflow: hidden;
    }

    .brand-mark::before {
      content: "";
      position: absolute;
      inset: 24%;
      border-radius: 999px;
      border: 1px solid rgba(244,201,106,0.7);
      opacity: 0.8;
    }

    .brand-thread {
      width: 2px;
      height: 70%;
      border-radius: 999px;
      background: linear-gradient(
        180deg,
        rgba(244,201,106,0.05),
        rgba(244,201,106,0.95),
        rgba(244,201,106,0.05)
      );
      box-shadow: 0 0 12px rgba(244,201,106,0.8);
    }

    .brand-text-top {
      font-size: 12px;
      letter-spacing: 0.22em;
      text-transform: uppercase;
      color: var(--text-soft);
    }

    .brand-text-main {
      font-size: 20px;
      letter-spacing: 0.24em;
      text-transform: uppercase;
      color: var(--accent-soft);
    }

    .brand-text-sub {
      font-size: 11px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--text-soft);
    }

    .header-right {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 6px;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--text-soft);
    }

    .flow-pill {
      padding: 4px 10px;
      border-radius: 999px;
      border: 1px solid rgba(244,201,106,0.4);
      background: linear-gradient(135deg, rgba(6,49,31,0.85), rgba(8,69,43,0.9));
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 11px;
      color: var(--accent-soft);
    }

    .flow-dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: radial-gradient(circle, #35f99d 0, #0f7e48 55%, #0b3b20 100%);
      box-shadow: 0 0 8px rgba(71,252,167,0.8);
    }

    .frame-body {
      padding: 20px 24px 22px;
      display: grid;
      grid-template-columns: minmax(0,1.25fr) minmax(0,1fr);
      gap: 18px;
    }

    .col {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .card {
      border-radius: 18px;
      background:
        radial-gradient(circle at top, rgba(244,201,106,0.16) 0, transparent 60%),
        linear-gradient(145deg, var(--bg-alt), #051b11);
      border: 1px solid rgba(17,108,67,0.95);
      box-shadow:
        0 14px 35px rgba(0,0,0,0.5),
        0 0 0 1px rgba(244,201,106,0.04);
      padding: 14px 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }

    .card-title {
      font-size: 12px;
      letter-spacing: 0.22em;
      text-transform: uppercase;
      color: var(--accent-soft);
    }

    .card-tag {
      font-size: 10px;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--text-soft);
    }

    .card-body {
      font-size: 13px;
      color: var(--text-main);
    }

    .status-line {
      font-size: 13px;
      color: var(--text-soft);
      margin-top: 6px;
    }

    .status-value {
      color: var(--accent-soft);
      font-weight: 500;
    }

    .pill-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }

    .freq-pill {
      font-size: 11px;
      padding: 4px 9px;
      border-radius: 999px;
      border: 1px solid rgba(244,201,106,0.35);
      background: linear-gradient(135deg, rgba(10,61,36,0.9), rgba(5,31,20,0.95));
      color: var(--accent-soft);
    }

    .collections-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 6px;
    }

    .collection-chip {
      font-size: 11px;
      padding: 4px 9px;
      border-radius: 999px;
      border: 1px solid rgba(244,201,106,0.3);
      background: rgba(9,45,27,0.85);
      color: var(--text-soft);
    }

    .log-area {
      font-size: 11px;
      color: var(--text-soft);
      max-height: 74px;
      overflow-y: auto;
      padding-right: 4px;
      scrollbar-width: thin;
      margin-top: 4px;
      line-height: 1.4;
    }

    .log-line { opacity: 0.9; }

    .frame-footer {
      padding: 10px 24px 12px;
      border-top: 1px solid rgba(244,201,106,0.1);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      font-size: 10px;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--text-soft);
    }

    .footer-left {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .footer-divider {
      width: 1px;
      height: 10px;
      background: rgba(244,201,106,0.5);
    }

    .footer-right {
      text-align: right;
    }

    @media (max-width: 840px) {
      .frame-body {
        grid-template-columns: minmax(0,1fr);
      }
    }

    @media (max-width: 600px) {
      body { padding: 16px 10px; }
      .frame-header { flex-direction: column; align-items: flex-start; }
      .header-right { align-items: flex-start; }
      .frame-footer { flex-direction: column; align-items: flex-start; }
      .footer-right { text-align: left; }
    }
  </style>
</head>
<body>
  <div class="frame">
    <header class="frame-header">
      <div class="brand-block">
        <div class="brand-mark">
          <div class="brand-thread"></div>
        </div>
        <div>
          <div class="brand-text-top">EnTrus Arts</div>
          <div class="brand-text-main">Flow Station</div>
          <div class="brand-text-sub">528 Hz - Live in Rhythm</div>
        </div>
      </div>
      <div class="header-right">
        <div class="flow-pill">
          <div class="flow-dot"></div>
          <span id="header-status-text">Core: aligning</span>
        </div>
        <div>Cloud Node - EnTrus Core</div>
      </div>
    </header>

    <main class="frame-body">
      <section class="col">
        <article class="card">
          <div class="card-header">
            <div class="card-title">Universe Status</div>
            <div class="card-tag">/universe/summary</div>
          </div>
          <div class="card-body">
            <div class="status-line">
              Health:
              <span class="status-value" id="universe-health">...</span>
            </div>
            <div class="status-line">
              Label:
              <span class="status-value" id="universe-label">...</span>
            </div>
          </div>
        </article>

        <article class="card">
          <div class="card-header">
            <div class="card-title">Event Log</div>
            <div class="card-tag">Live ping</div>
          </div>
          <div class="card-body">
            <div class="log-area" id="log-area">
              <div class="log-line">Waiting for first heartbeat...</div>
            </div>
          </div>
        </article>
      </section>

      <section class="col">
        <article class="card">
          <div class="card-header">
            <div class="card-title">Frequency Lines</div>
            <div class="card-tag">/frequency/lines</div>
          </div>
          <div class="card-body">
            <div class="pill-row" id="freq-row"></div>
          </div>
        </article>

        <article class="card">
          <div class="card-header">
            <div class="card-title">Apparel Collections</div>
            <div class="card-tag">/apparel/collections</div>
          </div>
          <div class="card-body">
            <div class="collections-list" id="collections-list"></div>
          </div>
        </article>
      </section>
    </main>

    <footer class="frame-footer">
      <div class="footer-left">
        <span>EnTrus System 2025</span>
        <div class="footer-divider"></div>
        <span>Cloud Flow Node</span>
      </div>
      <div class="footer-right">
        <div>Alignment: Forest Green - Morning Gold</div>
      </div>
    </footer>
  </div>

  <script>
    function logLine(text) {
      const log = document.getElementById('log-area');
      const line = document.createElement('div');
      line.className = 'log-line';
      line.textContent = text;
      log.appendChild(line);
      log.scrollTop = log.scrollHeight;
    }

    async function fetchUniverse() {
      try {
        const res = await fetch('/universe/summary');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        document.getElementById('universe-health').textContent = data.status || 'online';
        document.getElementById('universe-label').textContent = data.universe || 'EnTrus Core';
        document.getElementById('header-status-text').textContent = 'Core: ' + (data.status || 'online');
        logLine('Universe summary synced.');
      } catch (err) {
        document.getElementById('universe-health').textContent = 'offline';
        document.getElementById('universe-label').textContent = 'no response';
        document.getElementById('header-status-text').textContent = 'Core: offline';
        logLine('Universe summary failed: ' + err.message);
      }
    }

    async function fetchFrequencies() {
      try {
        const res = await fetch('/frequency/lines');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        const row = document.getElementById('freq-row');
        row.innerHTML = '';
        (data.frequencies || []).forEach(function (hz) {
          const pill = document.createElement('div');
          pill.className = 'freq-pill';
          pill.textContent = hz + ' Hz';
          row.appendChild(pill);
        });
        logLine('Frequency lines synced.');
      } catch (err) {
        logLine('Frequency sync failed: ' + err.message);
      }
    }

    async function fetchCollections() {
      try {
        const res = await fetch('/apparel/collections');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        const list = document.getElementById('collections-list');
        list.innerHTML = '';
        (data.collections || []).forEach(function (name) {
          const chip = document.createElement('div');
          chip.className = 'collection-chip';
          chip.textContent = name;
          list.appendChild(chip);
        });
        logLine('Apparel collections synced.');
      } catch (err) {
        logLine('Collections sync failed: ' + err.message);
      }
    }

    function syncAll() {
      fetchUniverse();
      fetchFrequencies();
      fetchCollections();
    }

    window.addEventListener('load', function () {
      logLine('Flow dashboard loaded. Syncing endpoints...');
      syncAll();
      setInterval(fetchUniverse, 15000);
    });
  </script>
</body>
</html>
"""


# -------------------------------------------------------------------
# FastAPI Routes
# -------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
  """Serve the Flow Station dashboard."""
  return HTMLResponse(DASHBOARD_HTML)


@app.get("/universe/summary")
async def universe_summary() -> dict:
  return {
    "status": "online",
    "universe": "EnTrus Cloud Flow Node"
  }


@app.get("/frequency/lines")
async def frequency_lines() -> dict:
  return {
    "frequencies": [285, 396, 528, 639, 741, 852]
  }


@app.get("/apparel/collections")
async def apparel_collections() -> dict:
  return {
    "collections": ["Protector", "Flow", "Drive", "Expression", "Seer"]
  } 
