/**
 * Panel de Costos — Agropecuaria El Faisán
 * -------------------------------------------------------
 * Lee un CSV público (publicado desde Google Sheets), detecta
 * automáticamente qué columna es la "etiqueta" (texto) y cuáles
 * son columnas numéricas (costos), y dibuja una cuadrícula de
 * fichas ("squares") con esos valores.
 *
 * No necesita que la hoja tenga una estructura fija: mientras
 * haya al menos una columna de texto y una columna numérica,
 * el panel se arma solo.
 */

const els = {
  grid: document.getElementById("grid"),
  totalCard: document.getElementById("total-card"),
  totalValue: document.getElementById("total-value"),
  totalLabel: document.getElementById("total-label"),
  status: document.getElementById("status"),
  updated: document.getElementById("updated"),
  search: document.getElementById("search"),
  refreshBtn: document.getElementById("refresh-btn"),
  companyName: document.getElementById("company-name"),
  tagline: document.getElementById("tagline"),
  location: document.getElementById("location"),
};

let rawRows = [];
let labelKey = null;
let numericKeys = [];

init();

function init() {
  els.companyName.textContent = CONFIG.COMPANY_NAME;
  els.tagline.textContent = CONFIG.TAGLINE;
  els.location.textContent = CONFIG.LOCATION_LABEL;

  els.refreshBtn.addEventListener("click", () => loadData(true));
  els.search.addEventListener("input", () => renderGrid(els.search.value));

  loadData();

  if (CONFIG.REFRESH_INTERVAL_MINUTES > 0) {
    setInterval(() => loadData(true), CONFIG.REFRESH_INTERVAL_MINUTES * 60 * 1000);
  }
}

async function loadData(isManualRefresh) {
  if (!CONFIG.SHEET_CSV_URL || CONFIG.SHEET_CSV_URL.includes("PASTE_YOUR")) {
    setStatus(
      "error",
      "Falta configurar el link de la hoja. Editá SHEET_CSV_URL en js/config.js."
    );
    return;
  }

  setStatus("loading", isManualRefresh ? "Actualizando datos…" : "Cargando datos…");

  try {
    const csvText = await fetchCsv(CONFIG.SHEET_CSV_URL);
    const parsed = Papa.parse(csvText, {
      header: true,
      dynamicTyping: true,
      skipEmptyLines: true,
    });

    if (parsed.errors && parsed.errors.length) {
      console.warn("Advertencias al leer el CSV:", parsed.errors);
    }

    rawRows = (parsed.data || []).filter((row) => Object.keys(row).length > 0);

    if (!rawRows.length) {
      setStatus("error", "La hoja no tiene filas de datos.");
      return;
    }

    detectColumns(rawRows);

    if (!labelKey || numericKeys.length === 0) {
      setStatus(
        "error",
        "No se pudo detectar una columna de texto y una columna numérica en la hoja."
      );
      return;
    }

    renderGrid(els.search.value);
    setStatus("ok", `${rawRows.length} filas cargadas`);
    els.updated.textContent = `Actualizado: ${new Date().toLocaleString(CONFIG.LOCALE)}`;
  } catch (err) {
    console.error(err);
    setStatus(
      "error",
      "No se pudo cargar la hoja. Revisá que el link CSV sea público y esté bien copiado."
    );
  }
}

async function fetchCsv(url) {
  const bustCache = url.includes("?") ? "&" : "?";
  const res = await fetch(`${url}${bustCache}_=${Date.now()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.text();
}

/** Decide which column is the label and which columns are numeric costs. */
function detectColumns(rows) {
  const keys = Object.keys(rows[0]);
  const numericScore = {};
  const textScore = {};

  keys.forEach((key) => {
    numericScore[key] = 0;
    textScore[key] = 0;
  });

  rows.forEach((row) => {
    keys.forEach((key) => {
      const val = row[key];
      if (val === null || val === undefined || val === "") return;
      if (typeof val === "number" && !Number.isNaN(val)) {
        numericScore[key]++;
      } else {
        textScore[key]++;
      }
    });
  });

  numericKeys = keys.filter((key) => numericScore[key] >= textScore[key] && numericScore[key] > 0);
  const remaining = keys.filter((key) => !numericKeys.includes(key));
  labelKey = remaining.sort((a, b) => textScore[b] - textScore[a])[0] || remaining[0] || keys[0];
}

function renderGrid(filterText) {
  const query = (filterText || "").trim().toLowerCase();
  const filtered = query
    ? rawRows.filter((row) => String(row[labelKey] ?? "").toLowerCase().includes(query))
    : rawRows;

  els.grid.innerHTML = "";

  if (!filtered.length) {
    els.grid.innerHTML = `<p class="empty">Sin resultados para "${escapeHtml(filterText)}".</p>`;
  }

  filtered.forEach((row, i) => {
    const card = document.createElement("article");
    card.className = "card";
    card.style.setProperty("--i", i % 12);

    const label = document.createElement("h3");
    label.className = "card-label";
    label.textContent = String(row[labelKey] ?? "—");
    card.appendChild(label);

    numericKeys.forEach((key) => {
      const wrap = document.createElement("div");
      wrap.className = "card-metric";

      if (numericKeys.length > 1) {
        const metricLabel = document.createElement("span");
        metricLabel.className = "metric-label";
        metricLabel.textContent = key;
        wrap.appendChild(metricLabel);
      }

      const value = document.createElement("span");
      value.className = "metric-value";
      value.textContent = formatCurrency(row[key]);
      wrap.appendChild(value);

      card.appendChild(wrap);
    });

    els.grid.appendChild(card);
  });

  renderTotal(filtered);
}

function renderTotal(rows) {
  // Only show a single grand-total hero card when there's exactly one
  // numeric column — with several numeric columns a single sum is ambiguous.
  if (numericKeys.length !== 1) {
    els.totalCard.classList.add("hidden");
    return;
  }
  const key = numericKeys[0];
  const sum = rows.reduce((acc, row) => acc + (Number(row[key]) || 0), 0);
  els.totalLabel.textContent = `Total · ${key}`;
  els.totalValue.textContent = formatCurrency(sum);
  els.totalCard.classList.remove("hidden");
}

function formatCurrency(value) {
  const num = Number(value);
  if (Number.isNaN(num)) return String(value ?? "—");
  const formatted = new Intl.NumberFormat(CONFIG.LOCALE, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
  return `${CONFIG.CURRENCY_SYMBOL} ${formatted}`;
}

function setStatus(kind, message) {
  els.status.textContent = message;
  els.status.className = `status status-${kind}`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
