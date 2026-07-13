/**
 * CONFIGURACIÓN DEL PANEL
 * -------------------------------------------------------
 * Edita los valores de aquí abajo para conectar tu propia
 * hoja de Google Sheets y ajustar cómo se muestran los datos.
 *
 * ¿Cómo obtener el link CSV de tu Google Sheet?
 * 1. Abre tu hoja en Google Sheets.
 * 2. Archivo > Compartir > Publicar en la web.
 * 3. En "Vincular", elige la hoja específica (no "Todo el documento").
 * 4. En "Tipo de contenido", elige "Valores separados por comas (.csv)".
 * 5. Pulsa "Publicar" y copia el link generado en SHEET_CSV_URL.
 */

const CONFIG = {
  // Link CSV publicado de tu Google Sheet
  SHEET_CSV_URL: "PASTE_YOUR_PUBLISHED_GOOGLE_SHEET_CSV_URL_HERE",

  // Nombre y lema que aparecen en el encabezado
  COMPANY_NAME: "Agropecuaria El Faisán",
  TAGLINE: "Panel de Costos",
  LOCATION_LABEL: "Santa Cruz, Bolivia",

  // Formato numérico / moneda
  CURRENCY_SYMBOL: "Bs",
  LOCALE: "es-BO",

  // Refresco automático de datos, en minutos (0 = desactivado)
  REFRESH_INTERVAL_MINUTES: 0,
};
