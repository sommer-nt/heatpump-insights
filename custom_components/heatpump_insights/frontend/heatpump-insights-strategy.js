// Heat Pump Insights – dashboard strategy.
// Use it with a new dashboard whose raw configuration is:
//   strategy:
//     type: custom:heatpump-insights
//     heat_pump: Wärmepumpe   # optional, if several heat pumps are configured
// The dashboard is generated from the integration's sensors and assigned roles.
// It only displays data: thermostat and setting tiles do not react to taps.

const TEXT = {
  de: {
    overview: "Übersicht", curve: "Heizkurve", rooms: "Räume",
    today: "Heute und letzte 7 Tage", findings: "Befunde", cycling24: "Takten – letzte 24 Stunden",
    perDay: "Starts und Laufzeit pro Tag", energy: "Strom pro Tag",
    curveNow: "Heizkurve", curve48: "Vorlauf und Außentemperatur – 48 Stunden",
    roomTemps: "Raumtemperatur und Soll", valves24: "Ventile – 24 Stunden",
    noFindings: "Keine Befunde.", outdoor: "Außen", setting: "Einstellung Steilheit",
    target: "Soll-Vorlauf", actual: "Ist-Vorlauf", power: "Leistung",
    compressor: "Verdichter", compressorNow: "Aktuell", compressor48: "Hochdruck und Heißgas – 48 Stunden",
    highPressure: "Hochdruck", hotGas: "Heißgas",
    compressorHint: "Nur Anzeige: Hochdruck und Heißgas steigen, wenn die Wärmepumpe nahe an ihren Grenzen " +
      "arbeitet, etwa bei Warmwasser mit hoher Temperatur. Eine Bewertung gegen die Herstellergrenzen ist geplant.",
    severity: { info: "Info", check: "Prüfen", act: "Handeln" },
    hint: "Für das *Warum* frag Claude mit dem Connector Heat Pump Insights. " +
      "„Prüfen“ heißt beobachten, „Handeln“ nur bei klarer Datenlage – und nur Einstellungen, nie Eingriffe an der Anlage.",
  },
  en: {
    overview: "Overview", curve: "Heating curve", rooms: "Rooms",
    today: "Today and last 7 days", findings: "Findings", cycling24: "Cycling – last 24 hours",
    perDay: "Starts and runtime per day", energy: "Electricity per day",
    curveNow: "Heating curve", curve48: "Flow and outdoor temperature – 48 hours",
    roomTemps: "Room temperature and setpoint", valves24: "Valves – 24 hours",
    noFindings: "No findings.", outdoor: "Outdoor", setting: "Slope setting",
    target: "Target flow", actual: "Actual flow", power: "Power",
    compressor: "Compressor", compressorNow: "Now", compressor48: "High pressure and hot gas – 48 hours",
    highPressure: "High pressure", hotGas: "Hot gas",
    compressorHint: "Display only: high pressure and hot gas rise when the heat pump works near its limits, " +
      "e.g. hot water at high temperatures. An assessment against the manufacturer's limits is planned.",
    severity: { info: "Info", check: "Check", act: "Act" },
    hint: "Ask Claude with the Heat Pump Insights connector for the *why*. " +
      "'Check' means watch, 'Act' only with clear data – and only settings, never physical work.",
  },
};

const NO_TAP = {
  tap_action: { action: "none" },
  icon_tap_action: { action: "none" },
  hold_action: { action: "none" },
};

function findingsMarkdown(entityIds, t) {
  const sev = JSON.stringify(t.severity);
  const lists = entityIds.map((e) => `(state_attr('${e}', 'findings') or [])`).join(" + ");
  return (
    `{% set sev = ${sev} %}{% set items = ${lists} %}` +
    `{% for f in items %}- **{{ sev.get(f.severity, f.severity) }}:** {{ f.message }}` +
    `{% if f.evidence %} _({{ f.evidence }})_{% endif %}\n{% else %}${t.noFindings}{% endfor %}` +
    `\n\n${t.hint}`
  );
}

function tile(entity, extra = {}) {
  return { type: "tile", entity, grid_options: { columns: 6 }, ...extra };
}

class HeatPumpInsightsStrategy extends HTMLElement {
  static async generate(config, hass) {
    const t = (hass.language || "en").startsWith("de") ? TEXT.de : TEXT.en;
    const configs = Object.entries(hass.states)
      .filter(([id, s]) => id.startsWith("sensor.") && s.attributes && s.attributes.roles && "valves_by_room" in s.attributes)
      .map(([id, s]) => ({ ...s, entity_id: id }));
    const cfg = configs.find((s) => !config.heat_pump || s.attributes.heat_pump === config.heat_pump) || configs[0];
    if (!cfg) {
      return {
        views: [{ title: "Heat Pump Insights", cards: [{ type: "markdown",
          content: "No Heat Pump Insights heat pump found. Add the integration first." }] }],
      };
    }
    const roles = cfg.attributes.roles;
    const deviceId = hass.entities[cfg.entity_id] && hass.entities[cfg.entity_id].device_id;
    const own = {};
    const valveOpen = {};
    for (const e of Object.values(hass.entities)) {
      if (e.platform !== "heatpump_insights" || e.device_id !== deviceId) continue;
      if (e.translation_key === "valve_open") {
        const st = hass.states[e.entity_id];
        if (st) valveOpen[st.attributes.room] = e.entity_id;
      } else if (e.translation_key) {
        own[e.translation_key] = e.entity_id;
      }
    }
    const has = (key) => Boolean(own[key]);

    // Overview
    const kpis = ["cycling_rating", "starts_today", "runtime_today", "starts_per_day", "run_time_median", "short_cycle_share"]
      .filter(has).map((k) => tile(own[k]));
    const findingSources = ["cycling_rating", "curve_slope", "overheated_rooms"].filter(has).map((k) => own[k]);
    const badges = [roles.outdoor_temp_entity, roles.power_entity].filter(Boolean)
      .map((entity) => ({ type: "entity", entity, show_name: true }));
    const overview = {
      title: t.overview, path: "overview", icon: "mdi:heat-pump", type: "sections", max_columns: 3, badges,
      sections: [
        { type: "grid", cards: [
          { type: "heading", heading: t.today, icon: "mdi:calendar-today" }, ...kpis,
          { type: "heading", heading: t.findings, heading_style: "subtitle" },
          { type: "markdown", content: findingsMarkdown(findingSources, t) },
        ] },
        { type: "grid", column_span: 2, cards: [
          { type: "heading", heading: t.cycling24, icon: "mdi:chart-timeline-variant" },
          { type: "history-graph", hours_to_show: 24, entities: [{ entity: roles.power_entity, name: t.power }],
            grid_options: { columns: "full", rows: 4 } },
          { type: "heading", heading: t.perDay, heading_style: "subtitle" },
          { type: "statistics-graph", entities: [own.starts_today, own.runtime_today].filter(Boolean),
            stat_types: ["max"], period: "day", days_to_show: 14, chart_type: "bar",
            grid_options: { columns: "full", rows: 4 } },
        ] },
      ],
    };
    const views = [overview];

    // Heating curve
    if (has("curve_slope")) {
      const curveTiles = [tile(own.curve_slope)];
      if (has("flow_deviation")) curveTiles.push(tile(own.flow_deviation));
      if (roles.curve_slope_entity) curveTiles.push(tile(roles.curve_slope_entity, { name: t.setting, ...NO_TAP }));
      const lines = [
        roles.circuit_flow_target_entity && { entity: roles.circuit_flow_target_entity, name: t.target, color: "orange" },
        (roles.circuit_flow_temp_entity || roles.flow_temp_entity) &&
          { entity: roles.circuit_flow_temp_entity || roles.flow_temp_entity, name: t.actual, color: "red" },
        roles.outdoor_temp_entity && { entity: roles.outdoor_temp_entity, name: t.outdoor, color: "teal" },
      ].filter(Boolean);
      views.push({
        title: t.curve, path: "curve", icon: "mdi:chart-bell-curve-cumulative", type: "sections", max_columns: 3,
        sections: [
          { type: "grid", cards: [{ type: "heading", heading: t.curveNow, icon: "mdi:tune-vertical" }, ...curveTiles] },
          { type: "grid", column_span: 2, cards: [
            { type: "heading", heading: t.curve48, icon: "mdi:thermometer-lines" },
            { type: "history-graph", hours_to_show: 48, entities: lines, grid_options: { columns: "full", rows: 5 } },
          ] },
        ],
      });
    }

    // Compressor (display only until an operating-limit analysis exists)
    const compressorLines = [
      roles.high_pressure_entity && { entity: roles.high_pressure_entity, name: t.highPressure },
      roles.hot_gas_temp_entity && { entity: roles.hot_gas_temp_entity, name: t.hotGas },
    ].filter(Boolean);
    if (compressorLines.length) {
      const graphs = compressorLines.map((line) => ({
        type: "history-graph", hours_to_show: 48, entities: [line], grid_options: { columns: "full", rows: 4 },
      }));
      if (roles.power_entity) {
        graphs.push({ type: "history-graph", hours_to_show: 48, entities: [{ entity: roles.power_entity, name: t.power }],
          grid_options: { columns: "full", rows: 3 } });
      }
      views.push({
        title: t.compressor, path: "compressor", icon: "mdi:gauge", type: "sections", max_columns: 3,
        sections: [
          { type: "grid", cards: [
            { type: "heading", heading: t.compressorNow, icon: "mdi:gauge" },
            ...compressorLines.map((line) => tile(line.entity, { name: line.name, ...NO_TAP })),
            { type: "markdown", content: t.compressorHint },
          ] },
          { type: "grid", column_span: 2, cards: [
            { type: "heading", heading: t.compressor48, icon: "mdi:chart-line" }, ...graphs,
          ] },
        ],
      });
    }

    // Rooms
    const roomIds = roles.room_entities || [];
    if (roomIds.length) {
      const roomCards = [];
      for (const id of roomIds) {
        const name = hass.states[id] ? hass.states[id].attributes.friendly_name : id;
        roomCards.push(tile(id, { state_content: ["current_temperature", "temperature"], ...NO_TAP }));
        const valve = valveOpen[name];
        roomCards.push(valve ? tile(valve) : { type: "markdown", content: "–", grid_options: { columns: 6 } });
      }
      const valveEntities = Object.values(cfg.attributes.valves_by_room || {});
      const side = [{ type: "heading", heading: t.valves24, icon: "mdi:valve" }];
      if (valveEntities.length) {
        side.push({ type: "history-graph", hours_to_show: 24, entities: valveEntities,
          grid_options: { columns: "full", rows: Math.max(4, Math.ceil(valveEntities.length * 0.7)) } });
      }
      views.push({
        title: t.rooms, path: "rooms", icon: "mdi:home-thermometer", type: "sections", max_columns: 3,
        sections: [
          { type: "grid", column_span: 2, cards: [{ type: "heading", heading: t.roomTemps, icon: "mdi:home-thermometer" }, ...roomCards] },
          { type: "grid", cards: side },
        ],
      });
    }
    return { title: "Heat Pump Insights", views };
  }
}

if (!customElements.get("ll-strategy-dashboard-heatpump-insights")) {
  customElements.define("ll-strategy-dashboard-heatpump-insights", HeatPumpInsightsStrategy);
}
