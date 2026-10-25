"""Find which sensors fill which role – for any heat pump, without a per-model list.

Home Assistant describes every entity the same way, whatever the vendor: domain, device
class, unit, name, translation key and the device it belongs to. Roles are recognised
from that description with keywords in several languages. The result is a ranked list
of candidates per role with the reasons, so a user (or an assistant) can confirm it.
Nothing is assigned here.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

TEMPERATURE_UNITS = {"°C", "°F", "K"}
POWER_UNITS = {"W", "kW", "MW"}
ENERGY_UNITS = {"Wh", "kWh", "MWh", "GJ", "MJ"}
PRESSURE_UNITS = {"bar", "mbar", "psi", "kPa", "MPa", "Pa", "hPa"}

# fmt: off
# Keyword tables are kept compact on purpose; one word per line would hide the structure.

# Words that say "this belongs to a heat pump / heating system" (names, devices, integrations).
HEATING_CONTEXT = (
    "heat pump", "heatpump", "waermepumpe", "warmepumpe", "wp", "pompe a chaleur", "pac",
    "warmtepomp", "varmepump", "lampopumppu", "pompa di calore", "bomba de calor",
    "compressor", "verdichter", "heating", "heizung", "chauffage", "verwarming",
    "stiebel", "isg", "vicare", "viessmann", "daikin", "onecta", "altherma", "aquarea",
    "panasonic", "heishamon", "vaillant", "mypyllant", "myvaillant", "nibe", "myuplink",
    "buderus", "bosch", "junkers", "mitsubishi", "melcloud", "ecodan", "thinq", "therma v",
    "samsung ehs", "toshiba", "yutaki", "luxtronik", "alpha innotec", "heliotherm", "idm",
    "ochsner", "ism7", "weishaupt", "dimplex", "waterkotte", "lambda", "kermi", "remeha",
    "ecoforest", "thermia", "ctc", "ivt", "ebusd", "wolf", "atlantic", "midea", "haier",
)

FLOW = ("flow", "supply", "vorlauf", "depart", "aanvoer", "framledning", "menovesi",
        "mandata", "impulsion", "outlet", "leaving", "feed")
RETURN = ("return", "ruecklauf", "rucklauf", "retour", "retur", "paluuvesi", "ritorno",
          "inlet", "entering")
CIRCUIT = ("heating circuit", "circuit", "heizkreis", "kreis", "hk", "hc", "zone", "z",
           "mischer", "mixing", "mk", "circuito", "kring")
TARGET = ("target", "soll", "set", "setpoint", "desired", "calculated", "berechnet",
          "required", "consigne", "richtwert", "requested", "demand")
DHW = ("dhw", "domestic", "hot water", "water heating", "warmwasser", "ww", "brauchwasser",
       "tank", "speicher", "boiler", "cylinder", "ecs", "sanitaire", "tapwater", "legionella")
BACKUP = ("nhz", "heizstab", "booster", "backup", "immersion", "zuheiz", "elektroheiz",
          "auxiliary", "appoint")
OUTDOOR = ("outdoor", "outside", "aussen", "exterieur", "exterior", "external", "buiten",
           "utomhus", "ute", "ulko", "esterna")
NOT_HEATING_WATER = ("solar", "brine", "sole", "source", "quelle")

ROLE_SPECS: dict[str, dict] = {
    "power_entity": {
        "domains": ("sensor",), "units": POWER_UNITS, "device_classes": ("power",),
        "need": (),
        "strong": ("heat pump", "heatpump", "waermepumpe", "warmepumpe", "wp", "compressor",
                   "verdichter", "pompe a chaleur", "pac", "warmtepomp", "varmepump",
                   "pompa di calore"),
        "weak": ("power", "leistung", "electric", "consumption", "aufnahme", "input", "total"),
        "negative": ("pv", "solar", "photovolta", "grid", "netz", "battery", "batterie",
                     "inverter ac", "house", "haus", "einspeisung", "export", "heat output",
                     "heating power", "thermal", "heizleistung", "waermeleistung", "produced",
                     "phase", "reactive", "blind", "apparent", "schein"),
    },
    "outdoor_temp_entity": {
        "domains": ("sensor",), "units": TEMPERATURE_UNITS, "device_classes": ("temperature",),
        "need": (OUTDOOR,), "strong": OUTDOOR, "weak": ("ambient", "air", "luft"),
        "negative": TARGET + ("average", "mittel", "feels", "dew", "taupunkt", "min", "max"),
    },
    "flow_temp_entity": {
        "domains": ("sensor",), "units": TEMPERATURE_UNITS, "device_classes": ("temperature",),
        "need": (FLOW,), "strong": FLOW, "weak": ("actual", "ist", "water", "wasser", "wp"),
        "negative": RETURN + TARGET + DHW + CIRCUIT + BACKUP + NOT_HEATING_WATER + ("floor",),
    },
    "return_temp_entity": {
        "domains": ("sensor",), "units": TEMPERATURE_UNITS, "device_classes": ("temperature",),
        "need": (RETURN,), "strong": RETURN, "weak": ("actual", "ist", "water", "wasser", "wp"),
        "negative": TARGET + DHW + BACKUP + NOT_HEATING_WATER + ("max", "min"),
    },
    "circuit_flow_temp_entity": {
        "domains": ("sensor",), "units": TEMPERATURE_UNITS, "device_classes": ("temperature",),
        "need": (CIRCUIT, FLOW + ("water temp", "actual temperature", "isttemperatur")),
        "strong": CIRCUIT + FLOW, "weak": ("actual", "ist", "water"),
        "negative": TARGET + DHW + RETURN + ("room", "raum", "solar"),
    },
    "circuit_flow_target_entity": {
        "domains": ("sensor", "number"), "units": TEMPERATURE_UNITS,
        "device_classes": ("temperature",),
        "need": (TARGET, FLOW + CIRCUIT + ("water",)), "strong": TARGET + FLOW + CIRCUIT,
        "weak": ("water",),
        "negative": DHW + RETURN + ("room", "raum", "comfort", "eco", "komfort", "min", "max",
                                    "solar", "cool", "kuehl"),
    },
    "heat_energy_entity": {
        "domains": ("sensor",), "units": ENERGY_UNITS, "device_classes": ("energy",),
        "need": (("produced", "generated", "heat", "waerme", "warme", "thermal", "yield",
                  "output", "heizen", "heating", "erzeugt", "chaleur", "warmte"),),
        "strong": ("produced", "generated", "thermal", "heat meter", "waermemenge",
                   "heat quantity", "erzeugt", "yield", "output"),
        "weak": ("heat", "waerme", "heating", "heizen"),
        "negative": ("active", "wirk", "consum", "verbrauch", "electric", "elektr", "strom",
                     "import", "grid", "netz", "pv", "solar", "cost", "kosten", "today",
                     "heute", "daily", "yesterday", "gestern", "cool", "kuehl") + DHW,
    },
    "curve_slope_entity": {
        "domains": ("number", "input_number", "sensor"), "units": {None, ""},
        "device_classes": (),
        "need": (("curve", "kurve", "slope", "steilheit", "steigung", "gradient", "pente",
                  "stooklijn", "rise"),),
        "strong": ("heating curve", "heizkurve", "slope", "steilheit", "steigung", "gradient",
                   "pente", "rise"),
        "weak": ("curve", "kurve", "hk", "hc", "circuit"),
        "negative": ("shift", "parallel", "niveau", "level", "offset", "verschiebung",
                     "fusspunkt", "cool", "kuehl") + DHW,
    },
    "high_pressure_entity": {
        "domains": ("sensor",), "units": PRESSURE_UNITS, "device_classes": ("pressure",),
        "need": (("high pressure", "hochdruck", "high side", "condens", "kondens",
                  "discharge pressure", "hd", "hp pressure", "haute pression"),),
        "strong": ("high pressure", "hochdruck", "condens", "kondens", "discharge pressure",
                   "haute pression"),
        "weak": ("refrigerant", "kaeltemittel", "pressure", "druck"),
        "negative": ("low", "nieder", "water", "wasser", "anlage", "system", "heating circuit",
                     "brine", "sole", "suction", "saug"),
    },
    "hot_gas_temp_entity": {
        "domains": ("sensor",), "units": TEMPERATURE_UNITS, "device_classes": ("temperature",),
        "need": (("hot gas", "heissgas", "hotgas", "discharge", "druckgas", "compressor outlet",
                  "verdichteraustritt", "compressor temp", "gaz chaud"),),
        "strong": ("hot gas", "heissgas", "hotgas", "discharge", "druckgas",
                   "verdichteraustritt", "gaz chaud"),
        "weak": ("compressor", "verdichter"),
        "negative": TARGET + ("suction", "saug", "max", "limit"),
    },
}
# fmt: on


@dataclass(slots=True)
class EntityInfo:
    entity_id: str
    name: str = ""
    device_class: str | None = None
    unit: str | None = None
    state_class: str | None = None
    platform: str = ""
    device_name: str = ""
    translation_key: str = ""
    available: bool = True

    @property
    def domain(self) -> str:
        return self.entity_id.split(".", 1)[0]


@dataclass(slots=True)
class Candidate:
    entity_id: str
    name: str
    score: float
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "score": round(self.score, 2),
            "reasons": self.reasons,
        }


def normalize(text: str) -> str:
    """Lower case, umlauts and accents folded, separators as spaces: 'Außen-Temp' → 'aussen temp'."""
    text = text.lower().replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"([a-z])(\d)", r"\1 \2", text)  # 'hk1' → 'hk 1'
    return " " + re.sub(r"[^a-z0-9]+", " ", text).strip() + " "


def _has(text: str, word: str) -> bool:
    # Short words (wp, hk, ww, z …) only as whole words; longer ones also inside German
    # compounds ('aussentemperatur', 'vorlaufsolltemperatur').
    if len(word) <= 3:
        return f" {word} " in text
    return word in text


def _matches(text: str, words) -> list[str]:
    return [w for w in words if _has(text, w)]


def _text(entity: EntityInfo) -> str:
    return normalize(
        " ".join(
            (entity.entity_id.split(".", 1)[-1], entity.name, entity.translation_key, entity.device_name)
        )
    )


def _context(entity: EntityInfo) -> bool:
    return bool(
        _matches(normalize(f"{entity.platform} {entity.device_name} {entity.entity_id}"), HEATING_CONTEXT)
    )


def score_entity(entity: EntityInfo, role: str) -> Candidate | None:
    spec = ROLE_SPECS[role]
    if entity.domain not in spec["domains"] or not entity.available:
        return None
    unit_ok = entity.unit in spec["units"]
    class_ok = bool(spec["device_classes"]) and entity.device_class in spec["device_classes"]
    if not (unit_ok or class_ok):
        return None
    text = _text(entity)
    for group in spec["need"]:
        if not _matches(text, group):
            return None
    strong = _matches(text, spec["strong"])
    weak = [w for w in _matches(text, spec["weak"]) if w not in strong]
    negative = _matches(text, spec["negative"])
    score = min(len(strong), 2) * 1.0 + min(len(weak), 2) * 0.3 - len(negative) * 1.5
    reasons = []
    if strong:
        reasons.append("name: " + ", ".join(strong))
    if weak:
        reasons.append("also: " + ", ".join(weak))
    if negative:
        reasons.append("against: " + ", ".join(negative))
    if _context(entity):
        score += 0.5
        reasons.append("belongs to a heating device or integration")
    if class_ok:
        score += 0.2
    if role == "heat_energy_entity":
        if entity.state_class == "total_increasing":
            score += 0.3
            reasons.append("meter reading (total_increasing)")
        if _has(text, "total") or _has(text, "gesamt"):
            score += 0.3
            reasons.append("lifetime total")
    if score <= 0:
        return None
    return Candidate(entity.entity_id, entity.name or entity.entity_id, score, reasons)


def discover_roles(entities: list[EntityInfo], limit: int = 3) -> dict[str, dict]:
    """Ranked candidates per role, and whether the best one is clear enough to suggest.

    ``suggested`` is set only when the best candidate scores well and clearly ahead of
    the next one; otherwise the user (or the assistant, asking the user) has to choose.
    """
    result = {}
    for role in ROLE_SPECS:
        candidates = [c for e in entities if (c := score_entity(e, role))]
        candidates.sort(key=lambda c: (-c.score, c.entity_id))
        best = candidates[0] if candidates else None
        runner_up = candidates[1].score if len(candidates) > 1 else 0.0
        clear = (
            best is not None and best.score >= 1.2 and best.score - runner_up >= 0.29
        )  # one extra weak word
        result[role] = {
            "suggested": best.entity_id if clear else None,
            "candidates": [c.as_dict() for c in candidates[:limit]],
        }
    _one_entity_one_role(result)
    return result


def _one_entity_one_role(result: dict[str, dict]) -> None:
    """A sensor can only mean one thing: if two roles suggest the same entity, keep the
    role where it scores higher."""
    owner: dict[str, tuple[str, float]] = {}
    for role, entry in result.items():
        entity_id = entry["suggested"]
        if entity_id is None:
            continue
        score = entry["candidates"][0]["score"]
        if entity_id in owner:
            other, other_score = owner[entity_id]
            loser = role if score <= other_score else other
            result[loser]["suggested"] = None
            if loser == other:
                owner[entity_id] = (role, score)
        else:
            owner[entity_id] = (role, score)


def room_candidates(entities: list[EntityInfo]) -> list[str]:
    """Climate entities that look like room thermostats rather than the heat pump itself."""
    rooms = []
    for entity in entities:
        if entity.domain != "climate" or not entity.available:
            continue
        text = _text(entity)
        if _context(entity) and not _matches(text, ("room", "raum", "thermostat", "zimmer")):
            continue  # e.g. the heat pump's own heating-circuit climate entity
        if _matches(text, DHW):
            continue
        rooms.append(entity.entity_id)
    return rooms
