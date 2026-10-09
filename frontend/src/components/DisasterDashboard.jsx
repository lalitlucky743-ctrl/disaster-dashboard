import React, {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  Bell,
  ChevronDown,
  ChevronRight,
  CloudRain,
  Crosshair,
  LogOut,
  MapPin,
  Menu,
  Minus,
  Navigation,
  Plus,
  Radio,
  RefreshCw,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Thermometer,
  TrendingUp,
  User,
  Volume2,
  VolumeX,
  X,
  Users,
  Zap,
} from "lucide-react";
import {
  Circle,
  CircleMarker,
  MapContainer,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";

import { dashboardApi } from "../api/dashboardApi";
import { aiApi } from "../api/aiApi";
import { useAuth } from "../context/AuthContext";

const API_BASE_URL = String(
  import.meta.env.VITE_API_URL || "https://disaster-dashboard-kgbb.onrender.com"
).replace(/\/$/, "");

const UTTARAKHAND_CENTER = [30.0668, 79.0193];
const DEFAULT_ZOOM = 7.25;

const WEATHER_CACHE_KEY = "disaster-dashboard:open-meteo:last-good-v3";
const WEATHER_CACHE_TTL_MS = 15 * 60 * 1000;
const WEATHER_REQUEST_GAP_MS = 2 * 60 * 1000;
const ML_REQUEST_GAP_MS = 10 * 60 * 1000;
const LANDSLIDE_ML_REQUEST_GAP_MS = 15 * 60 * 1000;

// ML is allowed to run in parallel, but the dashboard still caps concurrency
// so a Render instance is not overwhelmed. Results are committed as soon as
// each request completes instead of waiting for all districts.
const ML_CONCURRENCY = 3;
const LANDSLIDE_ML_CONCURRENCY = 3;
const ML_FETCH_TIMEOUT_MS = 45000;
const LOCATION_ML_CONCURRENCY = 2;
const LOCATION_FLOOD_ML_CACHE_KEY = "disaster-dashboard:location-flood-ml:last-good-v63";
const LOCATION_LANDSLIDE_ML_CACHE_KEY = "disaster-dashboard:location-landslide-ml:last-good-v3";
const ML_CACHE_TTL_MS = 10 * 60 * 1000;
const LANDSLIDE_ML_CACHE_TTL_MS = 15 * 60 * 1000;
const FLOOD_ML_CACHE_KEY = "disaster-dashboard:flood-ml:last-good-v63";
const LANDSLIDE_ML_CACHE_KEY = "disaster-dashboard:landslide-ml:last-good-v3";
const OFFICIAL_ALERT_REQUEST_TIMEOUT_MS = 8000;
const OFFICIAL_ALERT_REFRESH_MS = 10 * 1000;
const DASHBOARD_REFRESH_MS = 60 * 1000;

const RISK_CONFIG = {
  LOW: {
    label: "Low",
    color: "#22c55e",
    fill: "#22c55e",
    border: "border-emerald-500/30",
    bg: "bg-emerald-500/5",
    text: "text-emerald-400",
  },
  MEDIUM: {
    label: "Medium",
    color: "#eab308",
    fill: "#eab308",
    border: "border-yellow-500/30",
    bg: "bg-yellow-500/5",
    text: "text-yellow-400",
  },
  HIGH: {
    label: "High",
    color: "#f97316",
    fill: "#f97316",
    border: "border-orange-500/30",
    bg: "bg-orange-500/5",
    text: "text-orange-400",
  },
  CRITICAL: {
    label: "Critical",
    color: "#ef4444",
    fill: "#ef4444",
    border: "border-red-500/30",
    bg: "bg-red-500/5",
    text: "text-red-400",
  },
  UNKNOWN: {
    label: "Unavailable",
    color: "#64748b",
    fill: "#64748b",
    border: "border-slate-700",
    bg: "bg-slate-950/20",
    text: "text-slate-500",
  },
};

const ALERT_CONFIG = {
  CRITICAL: {
    label: "Critical",
    color: "#ef4444",
    border: "border-red-500/30",
    bg: "bg-red-500/5",
    text: "text-red-400",
  },
  HIGH: {
    label: "Orange / High",
    color: "#f97316",
    border: "border-orange-500/30",
    bg: "bg-orange-500/5",
    text: "text-orange-400",
  },
  WARNING: {
    label: "Yellow / Warning",
    color: "#eab308",
    border: "border-yellow-500/30",
    bg: "bg-yellow-500/5",
    text: "text-yellow-400",
  },
  INFO: {
    label: "Information",
    color: "#38bdf8",
    border: "border-sky-500/20",
    bg: "bg-sky-500/5",
    text: "text-sky-400",
  },
  UNSPECIFIED: {
    label: "Severity not provided",
    color: "#64748b",
    border: "border-slate-700",
    bg: "bg-slate-950/20",
    text: "text-slate-500",
  },
};

const TAB_CONFIG = [
  { id: "Dashboard", icon: ShieldAlert },
  { id: "Live Monitoring", icon: Radio },
  { id: "Risk Analytics", icon: TrendingUp },
  { id: "AI Intelligence", icon: Zap },
  { id: "Relief", icon: Crosshair },
];

const DISTRICT_HINDI = {
  Almora: "अल्मोड़ा",
  Bageshwar: "बागेश्वर",
  Chamoli: "चमोली",
  Champawat: "चंपावत",
  Dehradun: "देहरादून",
  Haridwar: "हरिद्वार",
  Nainital: "नैनीताल",
  "Pauri Garhwal": "पौड़ी गढ़वाल",
  Pithoragarh: "पिथौरागढ़",
  Rudraprayag: "रुद्रप्रयाग",
  "Tehri Garhwal": "टिहरी गढ़वाल",
  "Udham Singh Nagar": "उधम सिंह नगर",
  Uttarkashi: "उत्तरकाशी",
};

const STATIC_DISTRICT_LOCATIONS = {
  Almora: [
    ["kasar-devi", "Kasar Devi", "Locality", 29.6589, 79.6688],
    ["ranikhet", "Ranikhet", "Town", 29.6436, 79.4322],
    ["dwarahat", "Dwarahat", "Town", 29.7773, 79.4275],
  ],
  Bageshwar: [
    ["bageshwar-town", "Bageshwar", "Town", 29.837, 79.7724],
    ["kapkot", "Kapkot", "Town", 29.9498, 79.9019],
    ["garur", "Garur", "Town", 29.9754, 79.6965],
  ],
  Chamoli: [
    ["gopeshwar", "Gopeshwar", "Town", 30.4028, 79.3194],
    ["joshimath", "Joshimath", "Town", 30.5555, 79.564,],
    ["badrinath", "Badrinath", "Town", 30.7433, 79.4938],
  ],
  Champawat: [
    ["champawat-town", "Champawat", "Town", 29.3319, 80.0913],
    ["lohaghat", "Lohaghat", "Town", 29.4024, 80.0881],
    ["tanakpur", "Tanakpur", "Town", 29.0745, 80.111],
  ],
  Dehradun: [
    ["dehradun-city", "Dehradun", "City", 30.3165, 78.0322],
    ["mussoorie", "Mussoorie", "Town", 30.4598, 78.0664],
    ["rishikesh", "Rishikesh", "City", 30.0869, 78.2676],
  ],
  Haridwar: [
    ["haridwar-city", "Haridwar", "City", 29.9457, 78.1642],
    ["roorkee", "Roorkee", "City", 29.8543, 77.888],
    ["laksar", "Laksar", "Town", 29.758, 78.0404],
  ],
  Nainital: [
    ["nainital-town", "Nainital", "Town", 29.3919, 79.4542],
    ["haldwani", "Haldwani", "City", 29.2183, 79.513],
    ["bhimtal", "Bhimtal", "Town", 29.3446, 79.5637],
    ["ramnagar", "Ramnagar", "Town", 29.3946, 79.126],
  ],
  "Pauri Garhwal": [
    ["pauri-town", "Pauri", "Town", 30.1461, 78.7816],
    ["srinagar-pauri", "Srinagar", "City", 30.2226, 78.783],
    ["kotdwar", "Kotdwar", "City", 29.7463, 78.522],
  ],
  Pithoragarh: [
    ["pithoragarh-town", "Pithoragarh", "Town", 29.5829, 80.2182],
    ["dharchula", "Dharchula", "Town", 30.0706, 80.3638],
    ["munsiyari", "Munsiyari", "Town", 30.0677, 80.2392],
  ],
  Rudraprayag: [
    ["rudraprayag-town", "Rudraprayag", "Town", 30.2844, 78.9811],
    ["ukhimath", "Ukhimath", "Town", 30.5206, 79.1272],
    ["guptkashi", "Guptkashi", "Town", 30.6144, 79.0817],
  ],
  "Tehri Garhwal": [
    ["new-tehri", "New Tehri", "City", 30.3782, 78.4803],
    ["narendranagar", "Narendranagar", "Town", 30.1639, 78.2939],
    ["chamba-tehri", "Chamba", "Town", 30.341, 78.395],
  ],
  "Udham Singh Nagar": [
    ["rudrapur", "Rudrapur", "City", 28.9875, 79.4141],
    ["kashipur", "Kashipur", "City", 29.2104, 78.9619],
    ["sitarganj", "Sitarganj", "Town", 28.92, 79.702],
  ],
  Uttarkashi: [
    ["uttarkashi-town", "Uttarkashi", "Town", 30.7268, 78.4354],
    ["harsil", "Harsil", "Village", 30.7259, 78.6997],
    ["barkot", "Barkot", "Town", 30.8088, 78.206],
    ["gangotri", "Gangotri", "Pilgrimage", 30.9943, 78.9398],
  ],
};

const DISTRICTS = Object.entries({
  Almora: [29.5892, 79.6467],
  Bageshwar: [29.8404, 79.7694],
  Chamoli: [30.2937, 79.5603],
  Champawat: [29.3209, 80.0088],
  Dehradun: [30.3165, 78.0322],
  Haridwar: [29.9457, 78.1642],
  Nainital: [29.3919, 79.4542],
  "Pauri Garhwal": [29.8688, 78.8383],
  Pithoragarh: [29.5829, 80.2182],
  Rudraprayag: [30.2844, 78.9811],
  "Tehri Garhwal": [30.3012, 78.5661],
  "Udham Singh Nagar": [28.961, 79.5154],
  Uttarkashi: [30.7268, 78.4354],
}).map(([name, [lat, lng]], districtIndex) => ({
  id: name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, ""),
  name,
  lat,
  lng,
  score: null,
  risk: null,
  riskSource: null,
  alerts: null,
  landslideScore: null,
  landslideRisk: null,
  landslideRiskSource: null,
  landslidePrediction: null,
  landslideUpdatedAt: null,
  locations: (STATIC_DISTRICT_LOCATIONS[name] || []).map(
    ([id, locationName, type, locationLat, locationLng]) => ({
      id,
      name: locationName,
      type,
      lat: locationLat,
      lng: locationLng,
      score: null,
      risk: null,
      riskSource: null,
      mlPrediction: null,
      mlUpdatedAt: null,
      landslideScore: null,
      landslideRisk: null,
      landslideRiskSource: null,
      landslidePrediction: null,
      landslideUpdatedAt: null,
      district: name,
    })
  ),
  order: districtIndex,
}));

const DISTRICT_NAME_LOOKUP = new Map(
  DISTRICTS.map((district) => [district.name.toLowerCase(), district.name])
);

const LOCATION_ALIASES = {
  ranikhet: "Almora",
  dwarahat: "Almora",
  bhikiyasain: "Almora",
  someshwar: "Almora",
  kasar: "Almora",
  "kasar devi": "Almora",
  kapkot: "Bageshwar",
  garur: "Bageshwar",
  kanda: "Bageshwar",
  gopeshwar: "Chamoli",
  joshimath: "Chamoli",
  badrinath: "Chamoli",
  gairsain: "Chamoli",
  karnaprayag: "Chamoli",
  lohaghat: "Champawat",
  tanakpur: "Champawat",
  banbasa: "Champawat",
  mussoorie: "Dehradun",
  rishikesh: "Dehradun",
  vikasnagar: "Dehradun",
  doiwala: "Dehradun",
  chakrata: "Dehradun",
  roorkee: "Haridwar",
  laksar: "Haridwar",
  bhagwanpur: "Haridwar",
  manglaur: "Haridwar",
  haldwani: "Nainital",
  bhimtal: "Nainital",
  ramnagar: "Nainital",
  kaladhungi: "Nainital",
  bhowali: "Nainital",
  lalkuan: "Nainital",
  srinagar: "Pauri Garhwal",
  kotdwar: "Pauri Garhwal",
  lansdowne: "Pauri Garhwal",
  satpuli: "Pauri Garhwal",
  pauri: "Pauri Garhwal",
  dharchula: "Pithoragarh",
  gangolihat: "Pithoragarh",
  didihat: "Pithoragarh",
  berinag: "Pithoragarh",
  munsiyari: "Pithoragarh",
  ukhimath: "Rudraprayag",
  kedarnath: "Rudraprayag",
  guptkashi: "Rudraprayag",
  agastyamuni: "Rudraprayag",
  "new tehri": "Tehri Garhwal",
  narendranagar: "Tehri Garhwal",
  chamba: "Tehri Garhwal",
  devprayag: "Tehri Garhwal",
  tehri: "Tehri Garhwal",
  rudrapur: "Udham Singh Nagar",
  kashipur: "Udham Singh Nagar",
  kichha: "Udham Singh Nagar",
  sitarganj: "Udham Singh Nagar",
  gadarpur: "Udham Singh Nagar",
  bazpur: "Udham Singh Nagar",
  jaspur: "Udham Singh Nagar",
  gangotri: "Uttarkashi",
  yamunotri: "Uttarkashi",
  harsil: "Uttarkashi",
  barkot: "Uttarkashi",
  bhatwari: "Uttarkashi",
};

const HAZARD_HINDI = {
  landslide: "भूस्खलन (लैंडस्लाइड)",
  flood: "बाढ़",
  cloudburst: "बादल फटना",
  earthquake: "भूकंप",
  "forest fire": "जंगल की आग",
  fire: "आग",
  "heavy rain": "भारी बारिश",
  storm: "तूफ़ान",
};

const toFiniteNumber = (value) => {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

function normalizeRisk(value) {
  if (value === null || value === undefined) return null;
  const risk = String(value).trim().toUpperCase();
  if (risk === "LOW") return "LOW";
  if (risk === "MEDIUM" || risk === "MODERATE") return "MEDIUM";
  if (risk === "HIGH" || risk === "SEVERE") return "HIGH";
  if (risk === "CRITICAL" || risk === "EXTREME") return "CRITICAL";
  return null;
}

function getRiskConfig(risk) {
  return RISK_CONFIG[normalizeRisk(risk)] || RISK_CONFIG.UNKNOWN;
}

function getSeverityWeight(severity) {
  const weights = {
    CRITICAL: 4,
    HIGH: 3,
    WARNING: 2,
    INFO: 1,
    UNSPECIFIED: 0,
  };
  return weights[String(severity || "UNSPECIFIED").toUpperCase()] || 0;
}

function normalizeSeverity(value) {
  if (value === null || value === undefined || value === "") return null;
  const raw = String(value).trim().toUpperCase();

  if (["1", "RED", "CRITICAL", "EXTREME", "EMERGENCY"].includes(raw)) {
    return "CRITICAL";
  }
  if (["2", "ORANGE", "HIGH", "SEVERE"].includes(raw)) {
    return "HIGH";
  }
  if (["3", "YELLOW", "WARNING"].includes(raw)) return "WARNING";
  if (["4", "GREEN", "INFO", "INFORMATION"].includes(raw)) return "INFO";
  if (raw.includes("RED")) return "CRITICAL";
  if (raw.includes("ORANGE")) return "HIGH";
  if (raw.includes("YELLOW")) return "WARNING";
  if (raw.includes("GREEN")) return "INFO";
  return null;
}

function getAlertConfig(severity) {
  return ALERT_CONFIG[String(severity || "UNSPECIFIED").toUpperCase()] || ALERT_CONFIG.UNSPECIFIED;
}

function getAlertHazardType(alert) {
  const raw =
    alert?.hazard_type ??
    alert?.hazardType ??
    alert?.disaster_type ??
    alert?.disasterType ??
    alert?.event_type ??
    alert?.eventType ??
    alert?.risk_type ??
    alert?.riskType ??
    alert?.hazard ??
    alert?.disaster ??
    alert?.raw?.hazard_type ??
    alert?.raw?.hazardType ??
    alert?.raw?.disaster_type ??
    alert?.raw?.disasterType;

  if (typeof raw === "string" && raw.trim()) return raw.trim();

  const text = [
    alert?.title,
    alert?.description,
    alert?.area,
    alert?.location,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  if (/landslide|land slide|slope failure/.test(text)) return "Landslide";
  if (/flood|waterlogging|river overflow/.test(text)) return "Flood";
  if (/cloudburst/.test(text)) return "Cloudburst";
  if (/earthquake|seismic|tremor/.test(text)) return "Earthquake";
  if (/heavy rain|very heavy rain|extremely heavy rain|rainfall/.test(text)) {
    return "Heavy Rainfall";
  }
  if (/thunderstorm|lightning/.test(text)) return "Thunderstorm / Lightning";

  return null;
}

function getAlertArea(alert) {
  return String(
    alert?.location ?? alert?.area ?? alert?.district ?? ""
  ).trim();
}

function hazardToHindi(hazard) {
  if (!hazard) return null;
  const lower = String(hazard).toLowerCase();
  const matched = Object.entries(HAZARD_HINDI).find(([key]) => lower.includes(key));
  return matched ? matched[1] : hazard;
}

function isTrustedV63Prediction(prediction) {
  if (!prediction || typeof prediction !== "object") return false;

  const version = String(
    prediction.model_version ?? prediction.version ?? ""
  ).trim().toLowerCase();

  return (
    version.startsWith("real-data-v6.3") &&
    prediction.data_policy === "real_data_only" &&
    prediction.completed_daily_data_only === true
  );
}

function getLiveRiskScore(prediction) {
  if (!prediction || typeof prediction !== "object") return null;

  // V6.3 exposes the HIGH-class probability as confidence.
  // Prefer the probability fields over generic score fields so an older
  // backend risk_score cannot masquerade as the current V6.3 ML output.
  const probabilityValues = [
    prediction.confidence,
    prediction.flood_probability,
    prediction.floodProbability,
    prediction.probability,
    prediction.positive_probability,
  ];

  for (const value of probabilityValues) {
    const number = toFiniteNumber(value);
    if (number !== null) return Math.round(clamp(number <= 1 ? number * 100 : number, 0, 100));
  }

  const direct = [
    prediction.risk_score,
    prediction.riskScore,
    prediction.score,
  ];

  for (const value of direct) {
    const number = toFiniteNumber(value);
    if (number !== null) {
      return Math.round(clamp(number <= 1 ? number * 100 : number, 0, 100));
    }
  }

  const probabilities = prediction.probabilities;
  if (probabilities && typeof probabilities === "object") {
    const high =
      probabilities["1"] ??
      probabilities[1] ??
      probabilities.HIGH ??
      probabilities.high;
    const number = toFiniteNumber(high);
    if (number !== null) return Math.round(clamp(number <= 1 ? number * 100 : number, 0, 100));
  }

  return null;
}

function riskFromScore(score) {
  const number = toFiniteNumber(score);
  if (number === null) return null;
  if (number >= 80) return "CRITICAL";
  if (number >= 60) return "HIGH";
  if (number >= 30) return "MEDIUM";
  return "LOW";
}

function getLiveRiskLevel(prediction) {
  if (!prediction || typeof prediction !== "object") return null;
  const explicit = normalizeRisk(
    prediction.risk_level ??
      prediction.riskLevel ??
      prediction.risk ??
      prediction.level
  );
  return explicit || riskFromScore(getLiveRiskScore(prediction));
}

function extractPredictionTimestamp(prediction) {
  if (!prediction || typeof prediction !== "object") return null;
  return (
    prediction.predicted_at ??
    prediction.prediction_time ??
    prediction.created_at ??
    prediction.timestamp ??
    null
  );
}

function readPersistentPredictionCache(cacheKey, ttlMs) {
  if (typeof window === "undefined") {
    return { items: {}, savedAt: 0 };
  }

  try {
    const raw = window.localStorage.getItem(cacheKey);
    if (!raw) return { items: {}, savedAt: 0 };

    const parsed = JSON.parse(raw);
    const savedAt = Number(parsed?.savedAt || 0);
    if (!savedAt || Date.now() - savedAt > ttlMs) {
      return { items: {}, savedAt: 0 };
    }

    return {
      items: parsed?.items && typeof parsed.items === "object" ? parsed.items : {},
      savedAt,
    };
  } catch {
    return { items: {}, savedAt: 0 };
  }
}

function writePersistentPredictionCache(cacheKey, items) {
  if (typeof window === "undefined") return;

  try {
    window.localStorage.setItem(
      cacheKey,
      JSON.stringify({
        savedAt: Date.now(),
        items,
      })
    );
  } catch {
    // Storage is optional; live ML remains fully functional without it.
  }
}

function cacheItemToMap(cache) {
  const map = new Map();
  Object.entries(cache?.items || {}).forEach(([id, value]) => {
    if (value?.prediction) {
      map.set(id, {
        prediction: value.prediction,
        updatedAt: value.updatedAt || null,
      });
    }
  });
  return map;
}

function mapToCacheItems(map) {
  const items = {};
  map.forEach((value, id) => {
    if (!value?.prediction) return;
    items[id] = {
      prediction: value.prediction,
      updatedAt: value.updatedAt || null,
    };
  });
  return items;
}

function isFreshPredictionCacheEntry(entry, ttlMs) {
  if (!entry?.prediction || !entry?.updatedAt) return false;
  const updatedAt = new Date(entry.updatedAt).getTime();
  return Number.isFinite(updatedAt) && Date.now() - updatedAt < ttlMs;
}

function runWithConcurrency(queueRef, limit, task) {
  return new Promise((resolve, reject) => {
    const queue = queueRef.current;
    queue.pending.push({ task, resolve, reject });

    const pump = () => {
      while (queue.active < limit && queue.pending.length) {
        const next = queue.pending.shift();
        queue.active += 1;
        Promise.resolve()
          .then(next.task)
          .then(next.resolve, next.reject)
          .finally(() => {
            queue.active -= 1;
            pump();
          });
      }
    };

    pump();
  });
}

function isTrustedLandslidePrediction(prediction) {
  if (!prediction || typeof prediction !== "object") return false;
  const version = String(prediction.model_version ?? prediction.version ?? "").trim().toLowerCase();
  return version.startsWith("landslide-real-gis-v3") && prediction.real_data_only === true && prediction.completed_daily_data_only === true;
}

function getLandslideRiskScore(prediction) {
  if (!isTrustedLandslidePrediction(prediction)) return null;
  const values = [prediction.landslide_probability, prediction.risk_score, prediction.confidence];
  for (const value of values) {
    const number = toFiniteNumber(value);
    if (number !== null) return Math.round(clamp(number <= 1 ? number * 100 : number, 0, 100));
  }
  const classOne = prediction.probabilities?.["1"] ?? prediction.probabilities?.[1];
  const probability = toFiniteNumber(classOne);
  return probability === null ? null : Math.round(clamp(probability <= 1 ? probability * 100 : probability, 0, 100));
}

function getLandslideRiskLevel(prediction) {
  if (!isTrustedLandslidePrediction(prediction)) return null;
  return normalizeRisk(prediction.risk_level ?? prediction.riskLevel ?? prediction.risk) || riskFromScore(getLandslideRiskScore(prediction));
}

function extractLandslidePredictionTimestamp(prediction) {
  if (!prediction || typeof prediction !== "object") return null;
  return prediction.generated_at ?? prediction.predicted_at ?? prediction.prediction_time ?? prediction.created_at ?? prediction.timestamp ?? null;
}

function getWeatherSignal(weatherData) {
  const current = weatherData?.current || {};
  const currentRain = toFiniteNumber(current.rain);
  const todayRain = toFiniteNumber(current.today_rain);
  const todayProbability = toFiniteNumber(current.today_max_probability);
  const tomorrowProbability = toFiniteNumber(current.tomorrow_max_probability);

  if (currentRain !== null && currentRain >= 0.1) {
    return {
      kind: "now",
      severity: "WARNING",
      text: "पिछले घंटे में वर्षा दर्ज हुई",
    };
  }

  if (todayProbability !== null && todayProbability >= 40) {
    return {
      kind: "today",
      severity: "WARNING",
      text: "आज बारिश की संभावना",
    };
  }

  if (tomorrowProbability !== null && tomorrowProbability >= 40) {
    return {
      kind: "tomorrow",
      severity: "WARNING",
      text: "कल बारिश की संभावना",
    };
  }

  if (todayRain !== null && todayRain >= 20) {
    return {
      kind: "today",
      severity: "WARNING",
      text: "आज वर्षा हुई / अपेक्षित है",
    };
  }

  return null;
}

function formatRainNumbers(weatherData) {
  const current = weatherData?.current || {};
  const bits = [];

  const currentRain = toFiniteNumber(current.rain);
  const todayRain = toFiniteNumber(current.today_rain);
  const todayProbability = toFiniteNumber(current.today_max_probability);
  const tomorrowProbability = toFiniteNumber(current.tomorrow_max_probability);

  if (currentRain !== null) bits.push(`पिछले घंटे ${currentRain.toFixed(1)} mm`);
  if (todayRain !== null) bits.push(`आज ${todayRain.toFixed(1)} mm`);
  if (todayProbability !== null) bits.push(`आज ${Math.round(todayProbability)}%`);
  if (tomorrowProbability !== null) bits.push(`कल ${Math.round(tomorrowProbability)}%`);

  return bits.join(" · ") || "वर्षा डेटा उपलब्ध नहीं";
}

function formatRelativeTime(value) {
  if (!value) return "time unavailable";
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "time unavailable";

  const diff = Date.now() - timestamp;
  if (diff < 0) return "in future";
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function resolveDistrictsFromText(text) {
  if (!text) return [];
  const lower = String(text).toLowerCase();
  const found = new Set();

  const has = (word) => {
    const escaped = String(word).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`(^|[^a-z])${escaped}([^a-z]|$)`).test(lower);
  };

  DISTRICT_NAME_LOOKUP.forEach((canonical, key) => {
    if (has(key)) found.add(canonical);
  });

  Object.entries(LOCATION_ALIASES).forEach(([alias, canonical]) => {
    if (has(alias)) found.add(canonical);
  });

  return Array.from(found);
}

function alertMentionsName(alert, name) {
  if (!alert || !name) return false;
  const text = [
    alert.title,
    alert.description,
    alert.location,
    alert.area,
    alert.district,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  const target = String(name).toLowerCase().trim();
  if (!target) return false;
  return text.includes(target);
}

function normalizeAlerts(payload) {
  const rawItems = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.alerts)
    ? payload.alerts
    : Array.isArray(payload?.data)
    ? payload.data
    : Array.isArray(payload?.results)
    ? payload.results
    : [];

  const normalized = [];

  rawItems.forEach((raw, index) => {
    if (!raw || typeof raw !== "object") return;

    const title = String(
      raw.title ?? raw.name ?? raw.headline ?? raw.event ?? ""
    ).trim();
    const description = String(
      raw.description ?? raw.desc ?? raw.message ?? raw.details ?? ""
    ).trim();
    if (!title && !description) return;

    const area = String(
      raw.area ?? raw.area_desc ?? raw.areaDesc ?? raw.location ?? ""
    ).trim();
    const explicitDistrict = String(
      raw.district ?? raw.district_name ?? ""
    ).trim();
    const districts = resolveDistrictsFromText(
      [title, description, area, explicitDistrict].filter(Boolean).join(" ")
    );

    if (explicitDistrict) {
      const canonical = DISTRICT_NAME_LOOKUP.get(explicitDistrict.toLowerCase());
      if (canonical && !districts.includes(canonical)) districts.unshift(canonical);
    }

    const severity =
      normalizeSeverity(
        raw.severity ?? raw.severity_level ?? raw.color ?? raw.warning_level
      ) || "UNSPECIFIED";

    const bulletinId = String(
      raw.bulletinId ??
        raw.bulletin_id ??
        raw.id ??
        raw.guid ??
        raw.alert_id ??
        `official-alert-${index}-${title}`
    );

    const base = {
      ...raw,
      id: String(raw.id ?? bulletinId),
      bulletinId,
      title: title || description.slice(0, 100),
      description,
      severity,
      timestamp:
        raw.timestamp ??
        raw.published_at ??
        raw.publishedAt ??
        raw.pubDate ??
        raw.created_at ??
        null,
      valid_until:
        raw.valid_until ??
        raw.validUntil ??
        raw.expires ??
        raw.expiry ??
        null,
      source: raw.source ? String(raw.source).trim() : null,
      source_url:
        raw.source_url ?? raw.sourceUrl ?? raw.url ?? raw.link ?? null,
      area: area || null,
      location: raw.location ? String(raw.location).trim() : area || null,
      district: explicitDistrict || districts[0] || null,
      raw,
      isBulletin: Boolean(raw.isBulletin),
    };

    if (districts.length === 0) {
      normalized.push(base);
    } else {
      const seen = new Set();
      districts.forEach((district) => {
        const key = `${bulletinId}::${district}`;
        if (seen.has(key)) return;
        seen.add(key);
        normalized.push({
          ...base,
          district,
          id: `${bulletinId}::${district}`,
        });
      });
    }
  });

  const deduped = [];
  const seen = new Set();
  normalized.forEach((alert) => {
    const key = `${alert.bulletinId}::${alert.district || ""}::${alert.timestamp || ""}`;
    if (seen.has(key)) return;
    seen.add(key);
    deduped.push(alert);
  });

  return deduped;
}

function isAlertActive(alert) {
  if (!alert) return false;
  const expires = alert.valid_until ? new Date(alert.valid_until).getTime() : null;
  return !Number.isFinite(expires) || expires > Date.now();
}

function buildCurrentWeather(item) {
  const current = item?.current || {};
  const hourly = item?.hourly || {};
  const times = Array.isArray(hourly.time) ? hourly.time : [];
  const rain = Array.isArray(hourly.rain) ? hourly.rain : [];
  const precipitation = Array.isArray(hourly.precipitation)
    ? hourly.precipitation
    : [];
  const probability = Array.isArray(hourly.precipitation_probability)
    ? hourly.precipitation_probability
    : [];

  const today = new Date();
  const dateKey = (date) => {
    try {
      return new Intl.DateTimeFormat("en-CA", {
        timeZone: "Asia/Kolkata",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(date);
    } catch {
      return date.toISOString().slice(0, 10);
    }
  };

  const todayKey = dateKey(today);
  const yesterdayKey = dateKey(new Date(today.getTime() - 86400000));
  const tomorrowKey = dateKey(new Date(today.getTime() + 86400000));
  const fallbackHour = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    hourCycle: "h23",
  }).format(today);
  // Open-Meteo's rain/precipitation current values are preceding-hour totals,
  // not an instantaneous rain-rate. Use its current timestamp to exclude
  // future forecast hours from the "Rainfall · Today" accumulated value.
  const currentHourKey =
    String(current.time || "").slice(0, 13) || `${todayKey}T${fallbackHour}`;

  let todayRain = 0;
  let todayRainSamples = 0;
  let yesterdayRain = 0;
  let yesterdayRainSamples = 0;
  let todayMaxProbability = null;
  let tomorrowMaxProbability = null;

  times.forEach((rawTime, index) => {
    const timeKey = String(rawTime || "");
    if (timeKey.length < 10) return;

    const key = timeKey.slice(0, 10);
    const hourKey = timeKey.slice(0, 13);
    const rainValue = toFiniteNumber(rain[index]);
    const precipitationValue = toFiniteNumber(precipitation[index]);
    // Total precipitation includes rain and showers. Prefer it over the
    // narrower rain-only field to avoid under-reporting precipitation.
    const values = [rainValue, precipitationValue].filter((value) => value !== null);
    const hourlyPrecipitation = values.length ? Math.max(...values) : null;
    const probabilityValue = toFiniteNumber(probability[index]);

    if (
      key === todayKey &&
      hourKey <= currentHourKey &&
      hourlyPrecipitation !== null
    ) {
      todayRain += Math.max(0, hourlyPrecipitation);
      todayRainSamples += 1;
    }
    if (key === yesterdayKey && hourlyPrecipitation !== null) {
      yesterdayRain += Math.max(0, hourlyPrecipitation);
      yesterdayRainSamples += 1;
    }
    if (key === todayKey && probabilityValue !== null) {
      todayMaxProbability =
        todayMaxProbability === null
          ? probabilityValue
          : Math.max(todayMaxProbability, probabilityValue);
    }
    if (key === tomorrowKey && probabilityValue !== null) {
      tomorrowMaxProbability =
        tomorrowMaxProbability === null
          ? probabilityValue
          : Math.max(tomorrowMaxProbability, probabilityValue);
    }
  });

  const currentRainOnly = toFiniteNumber(current.rain);
  const currentPrecipitation = toFiniteNumber(current.precipitation);
  const lastHourPrecipitation =
    currentRainOnly !== null && currentPrecipitation !== null
      ? Math.max(currentRainOnly, currentPrecipitation)
      : currentPrecipitation ?? currentRainOnly;

  return {
    temperature: current.temperature_2m,
    humidity: current.relative_humidity_2m,
    precipitation: currentPrecipitation,
    // Kept as `rain` for the existing rain signals/cards, but the displayed
    // value is the more complete preceding-hour total when available.
    rain: lastHourPrecipitation,
    rain_only: currentRainOnly,
    wind_speed: current.wind_speed_10m,
    weather_code: current.weather_code,
    today_rain: todayRainSamples ? Number(todayRain.toFixed(1)) : null,
    previous_day_rain: yesterdayRainSamples ? Number(yesterdayRain.toFixed(1)) : null,
    today_max_probability: todayMaxProbability,
    tomorrow_max_probability: tomorrowMaxProbability,
  };
}

function buildWeatherBulletins(districts, weatherByDistrict) {
  const bulletins = [];

  (districts || []).forEach((district) => {
    const weather = weatherByDistrict?.[district.id];
    const signal = getWeatherSignal(weather);
    if (!signal) return;

    const current = weather?.current || {};
    const nowRain = toFiniteNumber(current.rain);
    const todayProbability = toFiniteNumber(current.today_max_probability);
    const tomorrowProbability = toFiniteNumber(current.tomorrow_max_probability);

    let message = "";
    if (signal.kind === "now") {
      message = `${district.name} में पिछले घंटे ${nowRain?.toFixed(1) ?? "—"} mm precipitation दर्ज हुई।`;
    } else if (signal.kind === "today") {
      message = `${district.name} में आज वर्षा की अधिकतम संभावना ${Math.round(
        todayProbability ?? 0
      )}% है।`;
    } else {
      message = `${district.name} में कल वर्षा की अधिकतम संभावना ${Math.round(
        tomorrowProbability ?? 0
      )}% है।`;
    }

    bulletins.push({
      id: `weather-${district.id}-${signal.kind}`,
      bulletinId: `weather-${district.id}-${signal.kind}`,
      district: district.name,
      title: message,
      description: `यह लाइव Open-Meteo forecast telemetry से बनाया गया weather signal है; यह ML flood prediction नहीं है।`,
      area: district.name,
      location: district.name,
      severity: signal.severity,
      timestamp: weather?.fetched_at || null,
      valid_until: null,
      source: "Open-Meteo",
      source_url: "https://open-meteo.com/",
      isBulletin: true,
    });
  });

  return bulletins;
}

function buildPlaceBoard(districts, alerts, weatherByDistrict, locationWeatherById) {
  return (districts || []).map((district) => {
    const districtAlerts = (alerts || []).filter(
      (alert) => alert.district === district.name || alertMentionsName(alert, district.name)
    );
    const sortedDistrictAlerts = [...districtAlerts].sort(
      (a, b) =>
        getSeverityWeight(b.severity) - getSeverityWeight(a.severity) ||
        new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime()
    );

    const cities = (district.locations || []).map((location) => {
      const cityAlerts = districtAlerts.filter((alert) => alertMentionsName(alert, location.name));
      const top = [...cityAlerts, ...districtAlerts].sort(
        (a, b) =>
          getSeverityWeight(b.severity) - getSeverityWeight(a.severity) ||
          new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime()
      )[0] || null;

      return {
        location,
        weather: locationWeatherById?.[location.id] || null,
        officialAlerts: cityAlerts,
        top,
        named: Boolean(cityAlerts.length),
      };
    });

    return {
      district,
      weather: weatherByDistrict?.[district.id] || null,
      officialAlerts: districtAlerts,
      top: sortedDistrictAlerts[0] || null,
      cities,
    };
  });
}

function normalizeDistrictFeed(payload) {
  const rawItems = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.districts)
    ? payload.districts
    : Array.isArray(payload?.data)
    ? payload.data
    : [];

  if (!rawItems.length) return DISTRICTS.map((district) => ({ ...district }));

  const byName = new Map(DISTRICTS.map((district) => [district.name.toLowerCase(), district]));
  const result = [];

  rawItems.forEach((raw) => {
    if (!raw || typeof raw !== "object") return;
    const incomingName = String(raw.name ?? raw.district ?? raw.district_name ?? "").trim();
    const template = byName.get(incomingName.toLowerCase());
    if (!template) return;

    // The dashboard district feed is NOT the source of truth for current ML.
    // Older deployments may still return stale risk_score/risk fields here.
    // We deliberately ignore those fields and only attach ML results returned
    // by the dedicated /api/ml/predict-risk endpoint below.
    const merged = {
      ...template,
      ...raw,
      id: template.id,
      name: template.name,
      lat: toFiniteNumber(raw.lat ?? raw.latitude) ?? template.lat,
      lng: toFiniteNumber(raw.lng ?? raw.longitude) ?? template.lng,
      score: null,
      risk: null,
      riskSource: null,
      mlPrediction: null,
      mlUpdatedAt: null,
      landslideScore: null,
      landslideRisk: null,
      landslideRiskSource: null,
      landslidePrediction: null,
      landslideUpdatedAt: null,
      locations: template.locations,
    };

    result.push(merged);
  });

  const known = new Set(result.map((district) => district.id));
  DISTRICTS.forEach((district) => {
    if (!known.has(district.id)) result.push({ ...district });
  });

  return result.sort((a, b) => a.order - b.order);
}

function mergeDistrictMl(districts, predictionsById) {
  return districts.map((district) => {
    const prediction = predictionsById[district.id];
    if (!prediction) return district;

    return {
      ...district,
      score: getLiveRiskScore(prediction),
      risk: getLiveRiskLevel(prediction),
      riskSource: "ML",
      mlPrediction: prediction,
      mlUpdatedAt:
        extractPredictionTimestamp(prediction) || new Date().toISOString(),
    };
  });
}

function mergeDistrictLandslideMl(districts, predictionsById) {
  return districts.map((district) => {
    const prediction = predictionsById[district.id];
    if (!prediction) return district;
    const score = getLandslideRiskScore(prediction);
    const risk = getLandslideRiskLevel(prediction);
    if (score === null || !risk) return district;
    return {
      ...district,
      landslideScore: score,
      landslideRisk: risk,
      landslideRiskSource: "ML",
      landslidePrediction: prediction,
      landslideUpdatedAt: extractLandslidePredictionTimestamp(prediction) || new Date().toISOString(),
    };
  });
}

function mergeLocationMl(locationsById, predictionsById) {
  const next = { ...locationsById };
  Object.entries(predictionsById).forEach(([id, prediction]) => {
    if (!prediction) return;
    next[id] = prediction;
  });
  return next;
}

function riskSourceLabel(place) {
  if (place?.riskSource !== "ML") return "Unavailable";
  if (!place?.mlUpdatedAt) return "ML";
  const age = Date.now() - new Date(place.mlUpdatedAt).getTime();
  return Number.isFinite(age) && age > ML_REQUEST_GAP_MS * 1.25
    ? "Last known ML"
    : "Live ML";
}

function StatusDot({ active = false, pulse = false }) {
  return (
    <span
      className={`inline-block w-1.5 h-1.5 rounded-full ${
        active ? "bg-emerald-400" : "bg-slate-600"
      } ${pulse ? "animate-pulse" : ""}`}
    />
  );
}

function SectionHeader({ title, subtitle, icon: Icon, action }) {
  return (
    <div className="flex items-start justify-between gap-3 mb-4">
      <div className="flex items-start gap-3 min-w-0">
        <div className="w-8 h-8 rounded-lg border border-slate-800 bg-slate-950/40 flex items-center justify-center shrink-0">
          <Icon className="w-4 h-4 text-sky-400" />
        </div>
        <div className="min-w-0">
          <div className="text-xs font-bold text-slate-200">{title}</div>
          {subtitle && <div className="text-[9px] text-slate-600 mt-1">{subtitle}</div>}
        </div>
      </div>
      {action}
    </div>
  );
}

function MetricCard({ icon: Icon, label, value, detail, tone = "sky", onClick }) {
  const toneClasses = {
    sky: "text-sky-400",
    red: "text-red-400",
    orange: "text-orange-400",
    yellow: "text-yellow-400",
    emerald: "text-emerald-400",
  };
  const content = (
    <>
      <div className="flex items-center justify-between gap-3">
        <span className={`text-[9px] font-bold uppercase tracking-widest ${toneClasses[tone] || toneClasses.sky}`}>
          {label}
        </span>
        <Icon className={`w-4 h-4 ${toneClasses[tone] || toneClasses.sky}`} />
      </div>
      <div className="text-xl font-black text-slate-100 mt-3">{value}</div>
      <div className="text-[9px] text-slate-600 mt-1 leading-relaxed">{detail}</div>
    </>
  );

  return onClick ? (
    <button
      type="button"
      onClick={onClick}
      className="text-left rounded-2xl border border-slate-800 bg-slate-900/80 p-4 hover:bg-slate-900 transition"
    >
      {content}
    </button>
  ) : (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">{content}</div>
  );
}

function RiskBadge({ risk }) {
  const config = getRiskConfig(risk);
  return (
    <span className={`px-2 py-1 rounded-md border ${config.border} ${config.text} text-[8px] font-bold uppercase`}>
      {config.label}
    </span>
  );
}

function SearchPanel({ query, districts, onSelect, onClose }) {
  const lower = String(query || "").trim().toLowerCase();
  const results = [];

  (districts || []).forEach((district) => {
    if (district.name.toLowerCase().includes(lower)) {
      results.push({ type: "District", ...district });
    }
    (district.locations || []).forEach((location) => {
      if (location.name.toLowerCase().includes(lower)) {
        results.push({
          type: "Location",
          ...location,
          district: district.name,
        });
      }
    });
  });

  return (
    <div className="absolute z-[1600] top-12 left-0 right-0 rounded-xl border border-slate-800 bg-slate-900 shadow-2xl overflow-hidden">
      <div className="max-h-80 overflow-y-auto p-1.5">
        {results.length === 0 ? (
          <div className="px-3 py-4 text-[10px] text-slate-600">No monitored area found.</div>
        ) : (
          results.slice(0, 12).map((result) => {
            const config = getRiskConfig(result.risk);
            return (
              <button
                key={`${result.type}-${result.id}`}
                type="button"
                onClick={() => {
                  onSelect(result);
                  onClose?.();
                }}
                className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-slate-800/70 flex items-center gap-3"
              >
                <MapPin className="w-3.5 h-3.5 text-sky-400 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-[10px] font-semibold text-slate-300 truncate">{result.name}</div>
                  <div className="text-[8px] text-slate-600 mt-0.5">
                    {result.type}
                    {result.district && result.type === "Location" ? ` · ${result.district}` : ""}
                  </div>
                </div>
                <span className={`text-[8px] font-bold ${config.text}`}>{result.risk ? config.label : "Unavailable"}</span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

function MapViewportController({ selectedPlace, resetSignal, zoomLevel }) {
  const map = useMap();
  const lastReset = useRef(resetSignal);

  useEffect(() => {
    if (!map) return;
    if (resetSignal !== lastReset.current) {
      lastReset.current = resetSignal;
      map.setView(UTTARAKHAND_CENTER, DEFAULT_ZOOM, { animate: true });
      return;
    }
    if (!selectedPlace) return;
    const lat = toFiniteNumber(selectedPlace.lat);
    const lng = toFiniteNumber(selectedPlace.lng);
    if (lat === null || lng === null) return;
    map.setView([lat, lng], zoomLevel, { animate: true });
  }, [map, selectedPlace, resetSignal, zoomLevel]);

  return null;
}

function MapZoomWatcher({ onZoom }) {
  useMapEvents({ zoomend: (event) => onZoom(event.target.getZoom()) });
  return null;
}

function MapClickCapture() {
  useMapEvents({ click: () => {} });
  return null;
}

function VisibleLocationPrefetch({ districts, zoom, onPrefetch }) {
  const map = useMap();

  useEffect(() => {
    if (zoom < 9 || typeof onPrefetch !== "function") return undefined;

    const prefetchVisible = () => {
      if (map.getZoom() < 9) return;
      const bounds = map.getBounds();
      const visible = [];

      (districts || []).forEach((district) => {
        (district.locations || []).forEach((location) => {
          const lat = toFiniteNumber(location.lat);
          const lng = toFiniteNumber(location.lng);
          if (lat === null || lng === null || !bounds.contains([lat, lng])) return;
          visible.push({ location, district });
        });
      });

      if (visible.length) onPrefetch(visible);
    };

    prefetchVisible();
    map.on("moveend", prefetchVisible);
    map.on("zoomend", prefetchVisible);
    return () => {
      map.off("moveend", prefetchVisible);
      map.off("zoomend", prefetchVisible);
    };
  }, [map, districts, zoom, onPrefetch]);

  return null;
}

function RiskMap({
  districts,
  selectedDisaster = "FLOOD",
  selectedRisk,
  onSelectDistrict,
  onSelectLocation,
  alerts,
  selectedPlace,
  mapResetSignal,
  onPrefetchLocations,
  locationMlLoadingByKey,
}) {
  const [mapZoom, setMapZoom] = useState(DEFAULT_ZOOM);

  const viewingLandslide = selectedDisaster === "LANDSLIDE";

  const filteredDistricts = useMemo(() => {
    if (selectedRisk === "ALL") return districts;
    return districts.filter((district) => {
      const risk = viewingLandslide ? district.landslideRisk : district.risk;
      return normalizeRisk(risk) === normalizeRisk(selectedRisk);
    });
  }, [districts, selectedRisk, viewingLandslide]);

  return (
    <div className="relative h-[520px] overflow-hidden rounded-2xl border border-slate-800 bg-slate-950">
      <MapContainer
        center={UTTARAKHAND_CENTER}
        zoom={DEFAULT_ZOOM}
        minZoom={6}
        maxZoom={18}
        scrollWheelZoom
        zoomControl={false}
        className="h-full w-full"
      >
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <MapToolbarBridge />
        <MapViewportController
          selectedPlace={selectedPlace}
          zoomLevel={selectedPlace?.type === "Location" ? 15 : 12}
          resetSignal={mapResetSignal}
        />
        <MapZoomWatcher onZoom={setMapZoom} />
        <MapClickCapture />
        <VisibleLocationPrefetch
          districts={filteredDistricts}
          zoom={mapZoom}
          onPrefetch={onPrefetchLocations}
        />

        {filteredDistricts.map((district) => {
          const displayRisk = viewingLandslide ? district.landslideRisk : district.risk;
          const displayScore = viewingLandslide ? district.landslideScore : district.score;
          const displaySource = viewingLandslide ? district.landslideRiskSource : district.riskSource;
          const config = getRiskConfig(displayRisk);
          const hasMl = displaySource === "ML" && displayRisk;
          const radius =
            displayRisk === "CRITICAL"
              ? 18000
              : displayRisk === "HIGH"
              ? 15000
              : displayRisk === "MEDIUM"
              ? 12000
              : 9000;

          return (
            <Fragment key={district.id}>
              <Circle
                center={[district.lat, district.lng]}
                radius={radius}
                pathOptions={{
                  color: hasMl ? config.color : "#475569",
                  fillColor: hasMl ? config.fill : "#334155",
                  fillOpacity: hasMl ? 0.24 : 0.08,
                  weight: 2,
                  dashArray: hasMl ? undefined : "5 6",
                }}
                eventHandlers={{ click: () => onSelectDistrict(district) }}
              />

              <CircleMarker
                center={[district.lat, district.lng]}
                radius={district.risk === "CRITICAL" ? 10 : 8}
                pathOptions={{
                  color: "#ffffff",
                  weight: 1.5,
                  fillColor: hasMl ? config.color : "#64748b",
                  fillOpacity: 1,
                }}
                eventHandlers={{ click: () => onSelectDistrict(district) }}
              >
                <Popup>
                  <div className="min-w-[205px] text-slate-900">
                    <div className="font-bold text-sm">{district.name}</div>
                    <div className="text-xs mt-1">
                      {viewingLandslide ? "Landslide ML risk" : "Flood ML risk"}: <strong>{hasMl ? config.label : "Unavailable"}</strong>
                    </div>
                    <div className="text-xs mt-1">
                      {viewingLandslide ? "Landslide ML score" : "Flood ML score"}: <strong>{hasMl && displayScore !== null ? `${displayScore}%` : "Unavailable"}</strong>
                    </div>
                    <div className="text-xs mt-1">
                      ML freshness: <strong>{hasMl ? "Live ML" : "Unavailable"}</strong>
                    </div>
                    <div className="text-xs mt-1">
                      Active official alerts: <strong>{district.alerts ?? "—"}</strong>
                    </div>
                  </div>
                </Popup>
              </CircleMarker>

              {mapZoom >= 9 &&
                (district.locations || []).map((location) => {
                  const locationPrediction = viewingLandslide ? location.landslidePrediction || null : location.mlPrediction || null;
                  const liveLocationRisk = viewingLandslide ? getLandslideRiskLevel(locationPrediction) : getLiveRiskLevel(locationPrediction);
                  const locationScore = viewingLandslide ? getLandslideRiskScore(locationPrediction) : getLiveRiskScore(locationPrediction);
                  const locationConfig = getRiskConfig(liveLocationRisk);
                  const locationCacheKey = `${district.id}::${location.id}`;
                  const locationMlLoading = Boolean(
                    locationMlLoadingByKey?.[`${locationCacheKey}::${viewingLandslide ? "landslide" : "flood"}`]
                  );
                  const hazard = getAlertHazardType(
                    (alerts || []).find((alert) => alertMentionsName(alert, location.name))
                  );

                  return (
                    <CircleMarker
                      key={location.id}
                      center={[location.lat, location.lng]}
                      radius={7}
                      pathOptions={{
                        color: "#ffffff",
                        weight: 1,
                        fillColor: liveLocationRisk ? locationConfig.color : "#64748b",
                        fillOpacity: 1,
                      }}
                      eventHandlers={{ click: () => onSelectLocation(location, district) }}
                    >
                      {mapZoom >= 11 && (
                        <Tooltip direction="top" offset={[0, -7]} opacity={0.95} permanent>
                          <span className="text-[10px] font-semibold">
                            {location.name} · {liveLocationRisk ? locationConfig.label : locationMlLoading ? "Loading live ML…" : "Unavailable"}
                            {hazard ? ` · ${hazard}` : ""}
                          </span>
                        </Tooltip>
                      )}
                      <Popup>
                        <div className="min-w-[195px] text-slate-900">
                          <div className="font-bold text-sm">{location.name}</div>
                          <div className="text-xs mt-1">{location.type}</div>
                          <div className="text-xs mt-1">
                            {viewingLandslide ? "Landslide ML risk" : "Flood ML risk"}: <strong>{liveLocationRisk || "Unavailable"}</strong>
                          </div>
                          <div className="text-xs mt-1">
                            {viewingLandslide ? "Landslide ML score" : "Flood ML score"}: <strong>{locationScore !== null ? `${locationScore}%` : "Unavailable"}</strong>
                          </div>
                          <div className="text-xs mt-1">
                            Hazard from official alert: <strong>{hazard || "Not provided"}</strong>
                          </div>
                          {!liveLocationRisk && (
                            <div className="text-[10px] mt-2 text-slate-500">
                              {locationMlLoading
                                ? "Fetching a genuine live ML prediction for this location…"
                                : "No fresh location-level ML result is available yet. When this point is visible at zoom 9+, the dashboard requests its real coordinate-based prediction; no default score is substituted."}
                            </div>
                          )}
                        </div>
                      </Popup>
                    </CircleMarker>
                  );
                })}
            </Fragment>
          );
        })}
      </MapContainer>

      {filteredDistricts.length === 0 && (
        <div className="absolute inset-0 z-[850] flex items-center justify-center pointer-events-none">
          <div className="max-w-sm mx-4 rounded-2xl border border-slate-700 bg-slate-950/95 px-5 py-4 text-center shadow-2xl">
            <MapPin className="w-5 h-5 text-slate-500 mx-auto mb-2" />
            <div className="text-xs font-semibold text-slate-300">No live ML district matches</div>
            <div className="text-[10px] text-slate-500 mt-1 leading-relaxed">
              The selected risk filter has no districts with that current ML level.
            </div>
          </div>
        </div>
      )}

      <div className="absolute z-[900] top-3 left-3 flex flex-col gap-1.5">
        <button
          type="button"
          title="Zoom in"
          onClick={() => document.dispatchEvent(new CustomEvent("disaster-map-zoom-in"))}
          className="w-9 h-9 rounded-lg border border-slate-700 bg-[#101827]/95 text-slate-300 hover:text-white hover:bg-slate-800 flex items-center justify-center"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          type="button"
          title="Zoom out"
          onClick={() => document.dispatchEvent(new CustomEvent("disaster-map-zoom-out"))}
          className="w-9 h-9 rounded-lg border border-slate-700 bg-[#101827]/95 text-slate-300 hover:text-white hover:bg-slate-800 flex items-center justify-center"
        >
          <Minus className="w-4 h-4" />
        </button>
      </div>

      <div className="absolute z-[900] bottom-3 left-3 rounded-xl border border-slate-700/80 bg-[#0b111c]/95 px-3 py-2.5 shadow-xl">
        <div className="text-[9px] uppercase tracking-widest text-slate-500 mb-2">ML risk visualization</div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
          {Object.entries(RISK_CONFIG)
            .filter(([key]) => key !== "UNKNOWN")
            .map(([key, config]) => (
              <div key={key} className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: config.color }} />
                <span className="text-[9px] text-slate-400">{config.label}</span>
              </div>
            ))}
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-500" />
            <span className="text-[9px] text-slate-500">Unavailable</span>
          </div>
        </div>
      </div>

      <div className="absolute z-[900] top-3 right-3 rounded-lg border border-slate-700 bg-[#0b111c]/90 px-2.5 py-1.5 text-[9px] text-slate-500">
        ZOOM {Math.round(mapZoom * 10) / 10}
      </div>
    </div>
  );
}

function useMapToolbarBridge() {
  const map = useMap();
  useEffect(() => {
    const zoomIn = () => map.zoomIn();
    const zoomOut = () => map.zoomOut();
    document.addEventListener("disaster-map-zoom-in", zoomIn);
    document.addEventListener("disaster-map-zoom-out", zoomOut);
    return () => {
      document.removeEventListener("disaster-map-zoom-in", zoomIn);
      document.removeEventListener("disaster-map-zoom-out", zoomOut);
    };
  }, [map]);
  return null;
}

function MapToolbarBridge() {
  useMapToolbarBridge();
  return null;
}

function Siren({
  soundOn,
  onToggle,
  hasAlarm,
  onRing,
}) {
  return (
    <button
      type="button"
      onClick={() => {
        if (!soundOn && hasAlarm) onRing?.(2);
        onToggle?.();
      }}
      className={`flex items-center gap-1 rounded-md border px-2 py-1 text-[9px] font-bold uppercase tracking-wider transition ${
        soundOn
          ? "border-red-500/40 bg-red-500/10 text-red-400"
          : "border-slate-700 text-slate-500 hover:text-slate-300"
      }`}
    >
      {soundOn ? <Volume2 className="h-3 w-3" /> : <VolumeX className="h-3 w-3" />}
      {soundOn ? "Siren ON" : "Siren OFF"}
    </button>
  );
}

function useSiren() {
  const ctxRef = useRef(null);
  const stopRef = useRef(null);

  const unlock = useCallback(() => {
    if (typeof window === "undefined") return null;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return null;
    if (!ctxRef.current) ctxRef.current = new AudioCtx();
    if (ctxRef.current.state === "suspended") {
      void ctxRef.current.resume().catch(() => {});
    }
    return ctxRef.current;
  }, []);

  const stop = useCallback(() => {
    try {
      stopRef.current?.();
    } catch {
      // Audio node may already be stopped.
    }
    stopRef.current = null;
  }, []);

  const ring = useCallback(
    (seconds = 3) => {
      const ctx = unlock();
      if (!ctx) return;
      stop();

      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      oscillator.type = "sawtooth";
      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      oscillator.connect(gain);
      gain.connect(ctx.destination);

      const start = ctx.currentTime;
      oscillator.frequency.setValueAtTime(600, start);
      for (let i = 0; i < seconds * 2; i += 1) {
        oscillator.frequency.linearRampToValueAtTime(
          i % 2 === 0 ? 1100 : 600,
          start + (i + 1) * 0.5
        );
      }

      oscillator.start(start);
      oscillator.stop(start + seconds);
      stopRef.current = () => {
        try {
          oscillator.stop();
        } catch {
          // Already stopped.
        }
      };
    },
    [stop, unlock]
  );

  useEffect(() => () => stop(), [stop]);

  return { unlock, ring, stop };
}

function HazardAlertPanel({ districts, alerts, onSelectDistrict, onSelectLocation }) {
  const { ring, stop, unlock } = useSiren();
  const [soundOn, setSoundOn] = useState(false);
  const [confirmed, setConfirmed] = useState([]);
  const trackerRef = useRef(new Map());

  useEffect(() => {
    const items = [];
    let shouldRing = false;
    const tracker = trackerRef.current;

    const visit = (place, district, isLocation) => {
      const prediction = place?.mlPrediction;
      const score = getLiveRiskScore(prediction);
      const freshness = place?.mlUpdatedAt || extractPredictionTimestamp(prediction);
      const id = `${isLocation ? "loc" : "dist"}-${place.id}`;
      const state = tracker.get(id) || {
        streak: 0,
        active: false,
        rung: false,
        lastUpdatedAt: null,
        score: null,
        hazard: null,
      };

      if (place?.riskSource === "ML" && score !== null && freshness && freshness !== state.lastUpdatedAt) {
        state.lastUpdatedAt = freshness;
        state.score = score;
        state.hazard =
          place.hazardType ||
          getAlertHazardType((alerts || []).find((alert) => alertMentionsName(alert, place.name))) ||
          state.hazard;

        if (score >= 85) {
          state.streak += 1;
        } else if (score < 80) {
          state.streak = 0;
          state.active = false;
          state.rung = false;
        } else if (!state.active) {
          state.streak = 0;
        }

        if (!state.active && state.streak >= 2) state.active = true;
      }

      tracker.set(id, state);
      if (!state.active || state.score === null) return;

      if (state.score >= 90 && !state.rung) {
        state.rung = true;
        shouldRing = true;
      }

      items.push({
        key: id,
        risk: state.score >= 90 ? "CRITICAL" : "HIGH",
        score: state.score,
        hazard: state.hazard,
        place,
        district,
        isLocation,
      });
    };

    (districts || []).forEach((district) => {
      visit(district, district, false);
      // Location-level ML is on-demand to control provider request volume.
      (district.locations || []).forEach((location) => visit(location, district, true));
    });

    items.sort((a, b) => b.score - a.score);
    setConfirmed((previous) => {
      const same =
        previous.length === items.length &&
        previous.every(
          (item, index) =>
            item.key === items[index].key &&
            item.score === items[index].score &&
            item.hazard === items[index].hazard
        );
      return same ? previous : items;
    });

    if (soundOn && shouldRing) ring(5);
  }, [districts, alerts, ring, soundOn]);

  const toggleSound = () => {
    if (soundOn) {
      stop();
      setSoundOn(false);
    } else {
      unlock();
      setSoundOn(true);
    }
  };

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-3 min-w-0 h-full">
      <SectionHeader
        title="High ML Alerts"
        subtitle="ML score ≥ 85% for two consecutive successful ML readings · siren ≥ 90%"
        icon={AlertOctagon}
        action={
          <Siren
            soundOn={soundOn}
            onToggle={toggleSound}
            hasAlarm={confirmed.some((item) => item.score >= 90)}
            onRing={ring}
          />
        }
      />

      {confirmed.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-950/30 px-3 py-6 text-center">
          <ShieldCheck className="mx-auto mb-2 h-5 w-5 text-emerald-400" />
          <div className="text-[11px] font-semibold text-slate-300">No high ML alert right now</div>
          <div className="mt-1 text-[9px] leading-relaxed text-slate-500">
            No live district prediction has crossed the ML alert threshold on two consecutive readings.
          </div>
        </div>
      ) : (
        <div className="space-y-2 max-h-[340px] overflow-y-auto pr-1">
          {confirmed.map((item) => {
            const config = getRiskConfig(item.risk);
            const hazardHi = hazardToHindi(item.hazard);
            const districtHi = DISTRICT_HINDI[item.district.name] || item.district.name;
            const areaName = item.isLocation
              ? `${item.place.name} (${districtHi})`
              : districtHi;

            return (
              <button
                key={item.key}
                type="button"
                onClick={() =>
                  item.isLocation
                    ? onSelectLocation(item.place, item.district)
                    : onSelectDistrict(item.district)
                }
                className={`w-full text-left rounded-xl border ${config.border} bg-slate-950/40 hover:bg-slate-800/70 transition p-2.5`}
              >
                <div className="flex items-start gap-2.5">
                  <AlertOctagon className={`mt-0.5 h-4 w-4 shrink-0 ${config.text} ${item.risk === "CRITICAL" ? "animate-pulse" : ""}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className={`text-[8px] font-bold uppercase tracking-wider ${config.text}`}>
                        {item.risk === "CRITICAL" ? "Critical ML Risk" : "High ML Risk"}
                      </span>
                      <span className="text-sm font-black" style={{ color: config.color }}>
                        {item.score}%
                      </span>
                    </div>
                    <div className="mt-1 text-[11px] font-semibold text-slate-200">
                      {hazardHi ? `${areaName} में ${hazardHi} risk signal है` : `${areaName} में ML risk बढ़ा हुआ है`}
                    </div>
                    <div className="mt-1.5 h-1 rounded-full bg-slate-900 overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-700" style={{ width: `${item.score}%`, backgroundColor: config.color }} />
                    </div>
                    <div className="mt-1 text-[9px] text-slate-500">
                      ML reading: {formatRelativeTime(item.place.mlUpdatedAt)}
                    </div>
                    <div className="mt-1.5 flex items-center gap-1 text-[8px] text-sky-400">
                      <MapPin className="h-2.5 w-2.5" /> क्लिक करके लाइव मैप पर देखें
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

function AlertPanel({ alerts, onAlertClick }) {
  if (!alerts.length) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-950/30 px-4 py-6 text-center">
        <ShieldCheck className="w-6 h-6 text-emerald-400 mx-auto mb-2" />
        <div className="text-xs font-semibold text-slate-300">No verified official alerts available</div>
        <div className="text-[10px] text-slate-500 mt-1">
          The official backend feed returned no active alerts in the latest successful response.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {alerts.map((alert) => {
        const config = getAlertConfig(alert.severity);
        const small = Boolean(alert.isBulletin);
        return (
          <button
            key={alert.id}
            type="button"
            onClick={() => onAlertClick?.(alert)}
            className={`w-full text-left rounded-xl border ${config.border} ${config.bg} hover:bg-slate-800/60 transition p-3`}
          >
            <div className="flex items-start gap-3">
              <div className="mt-0.5 w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: config.color }} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className={`${small ? "text-[8px]" : "text-[9px]"} font-bold uppercase tracking-wider ${config.text}`}>
                    {alert.isBulletin ? "मौसम बुलेटिन" : getAlertHazardType(alert) || "Official Alert"}
                  </span>
                  <span className={`${small ? "text-[8px]" : "text-[9px]"} text-slate-500`}>
                    {formatRelativeTime(alert.timestamp)}
                  </span>
                </div>
                <div className={`${small ? "text-[10px]" : "text-xs"} font-semibold text-slate-200 mt-1`}>{alert.title}</div>
                {alert.description && (
                  <p className={`${small ? "text-[9px]" : "text-[10px]"} text-slate-500 mt-1 leading-relaxed`}>
                    {alert.description}
                  </p>
                )}
                <div className={`${small ? "text-[8px]" : "text-[9px]"} flex flex-wrap items-center gap-3 mt-2 text-slate-500`}>
                  {getAlertArea(alert) && (
                    <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{getAlertArea(alert)}</span>
                  )}
                  {alert.source && <span>{alert.source}</span>}
                  {alert.valid_until && <span>Valid until {new Date(alert.valid_until).toLocaleString()}</span>}
                </div>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function DistrictAlertBoard({ rows, officialStatus, onSelectDistrict, onSelectLocation }) {
  const [open, setOpen] = useState({});
  const officialReady = officialStatus === "live" || officialStatus === "empty";

  const statusText = (top) => {
    if (top) return `${getAlertConfig(top.severity).label} — ${top.title}`;
    return officialReady ? "No official alert" : "Checking official feed…";
  };

  return (
    <div className="space-y-2">
      {rows.map((row) => {
        const config = row.top ? getAlertConfig(row.top.severity) : null;
        const signal = getWeatherSignal(row.weather);
        const isOpen = Boolean(open[row.district.id]);

        return (
          <div key={row.district.id} className="rounded-xl border border-slate-800 bg-slate-950/30">
            <div className="flex items-stretch">
              <button
                type="button"
                onClick={() => onSelectDistrict(row.district)}
                className="flex-1 min-w-0 flex items-center gap-3 p-3 text-left hover:bg-slate-900/60 rounded-l-xl transition"
              >
                <div className="w-1.5 self-stretch rounded-full shrink-0" style={{ backgroundColor: config?.color || "#334155" }} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold text-slate-200">{row.district.name}</span>
                    <span className="text-[10px] text-slate-500">{DISTRICT_HINDI[row.district.name] || ""}</span>
                    {signal && (
                      <span className="text-[8px] font-bold px-1.5 py-0.5 rounded border border-yellow-500/20 text-yellow-400">
                        {signal.text}
                      </span>
                    )}
                  </div>
                  <div className={`text-[10px] mt-1 ${config?.text || "text-slate-500"}`}>{statusText(row.top)}</div>
                  <div className="text-[9px] text-slate-500 mt-1">{formatRainNumbers(row.weather)}</div>
                </div>
                <span className={`shrink-0 text-[9px] font-bold ${config?.text || "text-slate-600"}`}>
                  {row.officialAlerts.length} alert{row.officialAlerts.length === 1 ? "" : "s"}
                </span>
              </button>

              {row.cities.length > 0 && (
                <button
                  type="button"
                  onClick={() => setOpen((previous) => ({ ...previous, [row.district.id]: !previous[row.district.id] }))}
                  className="px-3 border-l border-slate-800 text-[9px] text-slate-500 hover:text-slate-200 flex items-center gap-1 rounded-r-xl"
                >
                  {row.cities.length} locations
                  <ChevronDown className={`w-3 h-3 transition ${isOpen ? "rotate-180" : ""}`} />
                </button>
              )}
            </div>

            {isOpen && (
              <div className="border-t border-slate-800 divide-y divide-slate-800/60">
                {row.cities.map((city) => {
                  const citySignal = getWeatherSignal(city.weather);
                  const cityTop = city.top;
                  return (
                    <button
                      key={city.location.id}
                      type="button"
                      onClick={() => onSelectLocation(city.location, row.district)}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-slate-900/60 transition"
                    >
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: cityTop ? getAlertConfig(cityTop.severity).color : "#334155" }} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[11px] font-semibold text-slate-300">{city.location.name}</span>
                          <span className="text-[9px] text-slate-600">{city.location.type}</span>
                          {citySignal && <span className="text-[8px] font-bold px-1.5 py-0.5 rounded border border-yellow-500/20 text-yellow-400">{citySignal.text}</span>}
                        </div>
                        <div className="text-[9px] mt-0.5 text-slate-500">
                          {cityTop ? `${getAlertConfig(cityTop.severity).label} (${city.named ? "location named" : "district alert"})` : officialReady ? "No official alert" : "Checking official feed…"}
                        </div>
                        <div className="text-[9px] text-slate-600 mt-0.5">{formatRainNumbers(city.weather)}</div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function AIWorkspace({ aiQuery, setAiQuery, aiResponse, isGenerating, aiStatus, onAsk }) {
  const suggestions = [
    "Why is the selected area currently at risk?",
    "Which monitored regions need attention?",
    "Explain the current weather conditions.",
    "What official alerts are currently active?",
  ];

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center">
              <Zap className="w-4 h-4 text-sky-400" />
            </div>
            <div>
              <div className="text-xs font-bold text-slate-200">Disaster Intelligence AI</div>
              <div className={`flex items-center gap-1.5 text-[9px] mt-0.5 ${aiStatus === "operational" ? "text-emerald-400" : aiStatus === "degraded" ? "text-red-400" : "text-slate-500"}`}>
                <StatusDot active={aiStatus === "operational"} />
                {aiStatus === "operational" ? "AI engine operational" : aiStatus === "degraded" ? "AI engine unavailable" : "AI engine ready to query"}
              </div>
            </div>
          </div>
        </div>

        <div className="p-5">
          <div className="rounded-2xl border border-sky-500/10 bg-sky-500/[0.03] p-4 min-h-[180px]">
            {isGenerating ? (
              <div className="flex items-center gap-3 text-sky-400">
                <RefreshCw className="w-4 h-4 animate-spin" />
                <div>
                  <div className="text-xs font-semibold">Analyzing intelligence data...</div>
                  <div className="text-[10px] text-slate-600 mt-1">Querying FastAPI intelligence layer.</div>
                </div>
              </div>
            ) : (
              <>
                <div className="text-[9px] uppercase tracking-widest text-sky-400/70 mb-2">AI Analysis</div>
                <p className="text-xs leading-6 text-slate-300 whitespace-pre-wrap">
                  {aiResponse || "Ask the Disaster Intelligence engine about risk, alerts, weather, locations or monitored regions."}
                </p>
              </>
            )}
          </div>

          <div className="mt-5">
            <div className="text-[9px] uppercase tracking-widest text-slate-600 mb-2">Suggested queries</div>
            <div className="flex flex-wrap gap-2">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => setAiQuery(suggestion)}
                  className="px-3 py-2 rounded-lg border border-slate-800 bg-slate-900/50 hover:bg-slate-800 text-[10px] text-slate-400 hover:text-slate-200 transition"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-5 relative">
            <textarea
              value={aiQuery}
              onChange={(event) => setAiQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  onAsk();
                }
              }}
              rows={3}
              placeholder="Ask Disaster Intelligence..."
              className="w-full resize-none rounded-2xl border border-slate-800 bg-slate-950 px-4 py-3 pr-12 text-xs text-slate-200 placeholder:text-slate-700 outline-none focus:border-sky-500/50"
            />
            <button
              type="button"
              disabled={isGenerating || !aiQuery.trim()}
              onClick={onAsk}
              className="absolute right-3 bottom-3 w-8 h-8 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center"
            >
              <Send className="w-3.5 h-3.5 text-white" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

async function fetchOfficialAlerts() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), OFFICIAL_ALERT_REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE_URL}/api/alerts`, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
      cache: "no-store",
    });

    if (!response.ok) throw new Error(`Official alert API ${response.status}`);
    const payload = await response.json();
    return normalizeAlerts(payload).filter(isAlertActive);
  } catch (error) {
    if (error?.name === "AbortError") throw new Error("Official alert request timed out.");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

export default function DisasterDashboard() {
  const { user, logout } = useAuth();

  const [activeTab, setActiveTab] = useState("Dashboard");
  const [baseDistricts, setBaseDistricts] = useState(() => DISTRICTS.map((district) => ({ ...district })));
  const [weatherByDistrict, setWeatherByDistrict] = useState({});
  const [locationWeatherById, setLocationWeatherById] = useState({});
  const [alerts, setAlerts] = useState([]);
  const [officialAlertStatus, setOfficialAlertStatus] = useState("loading");
  const [overview, setOverview] = useState(null);
  const [apiStatus, setApiStatus] = useState("loading");
  const [weatherStatus, setWeatherStatus] = useState("loading");
  const [mlStatus, setMlStatus] = useState("idle");
  const [landslideStatus, setLandslideStatus] = useState("idle");
  const [locationMlLoadingByKey, setLocationMlLoadingByKey] = useState({});
  const [weatherError, setWeatherError] = useState("");
  const [apiError, setApiError] = useState("");
  const [selectedRisk, setSelectedRisk] = useState("ALL");
  const [selectedDisaster, setSelectedDisaster] = useState("ALL");
  const [selectedPlace, setSelectedPlace] = useState(null);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [mapResetSignal, setMapResetSignal] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [aiQuery, setAiQuery] = useState("");
  const [aiResponse, setAiResponse] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [aiStatus, setAiStatus] = useState("ready");
  const [refreshing, setRefreshing] = useState(false);
  const [lastSync, setLastSync] = useState(null);

  const searchRef = useRef(null);
  const selectedPlaceRef = useRef(null);
  const baseDistrictsRef = useRef(baseDistricts);
  const weatherByDistrictRef = useRef(weatherByDistrict);
  const weatherSyncInFlightRef = useRef(false);
  const mlSyncInFlightRef = useRef(false);
  const officialAlertSyncInFlightRef = useRef(false);
  const lastWeatherRequestAtRef = useRef(0);
  const lastMlRequestAtRef = useRef(0);
  const lastLandslideRequestAtRef = useRef(0);
  const mlPredictionCacheRef = useRef(
    cacheItemToMap(readPersistentPredictionCache(FLOOD_ML_CACHE_KEY, ML_CACHE_TTL_MS))
  );
  const landslidePredictionCacheRef = useRef(
    cacheItemToMap(
      readPersistentPredictionCache(
        LANDSLIDE_ML_CACHE_KEY,
        LANDSLIDE_ML_CACHE_TTL_MS
      )
    )
  );
  const landslideSyncInFlightRef = useRef(false);
  const locationFloodPredictionCacheRef = useRef(
    cacheItemToMap(readPersistentPredictionCache(LOCATION_FLOOD_ML_CACHE_KEY, ML_CACHE_TTL_MS))
  );
  const locationLandslidePredictionCacheRef = useRef(
    cacheItemToMap(readPersistentPredictionCache(LOCATION_LANDSLIDE_ML_CACHE_KEY, LANDSLIDE_ML_CACHE_TTL_MS))
  );
  const locationFloodInFlightRef = useRef(new Set());
  const locationLandslideInFlightRef = useRef(new Set());
  const locationFloodQueueRef = useRef({ active: 0, pending: [] });
  const locationLandslideQueueRef = useRef({ active: 0, pending: [] });

  useEffect(() => {
    selectedPlaceRef.current = selectedPlace;
  }, [selectedPlace]);

  useEffect(() => {
    baseDistrictsRef.current = baseDistricts;
  }, [baseDistricts]);

  useEffect(() => {
    weatherByDistrictRef.current = weatherByDistrict;
  }, [weatherByDistrict]);

  const districts = useMemo(() => {
    const counts = {};
    if (officialAlertStatus === "live" || officialAlertStatus === "empty") {
      alerts.forEach((alert) => {
        if (alert.district) counts[alert.district] = (counts[alert.district] || 0) + 1;
      });
    }
    return baseDistricts.map((district) => ({
      ...district,
      alerts:
        officialAlertStatus === "live" || officialAlertStatus === "empty"
          ? counts[district.name] || 0
          : null,
    }));
  }, [baseDistricts, alerts, officialAlertStatus]);

  const validDistricts = useMemo(
    () =>
      districts.filter(
        (district) =>
          toFiniteNumber(district.lat) !== null && toFiniteNumber(district.lng) !== null
      ),
    [districts]
  );

  const fetchBackendWeather = useCallback(async (url, label, timeoutMs = 25000) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        method: "GET",
        cache: "no-store",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });

      if (!response.ok) {
        let detail = "";
        try {
          const body = await response.json();
          detail = body?.detail ? `: ${body.detail}` : "";
        } catch {
          // Keep status-only errors when there is no JSON body.
        }
        throw new Error(`Weather backend ${label} failed: ${response.status}${detail}`);
      }
      return await response.json();
    } finally {
      clearTimeout(timer);
    }
  }, []);

  const saveWeatherCache = useCallback((districtsValue, locationsValue) => {
    try {
      const current = JSON.parse(localStorage.getItem(WEATHER_CACHE_KEY) || "null");
      localStorage.setItem(
        WEATHER_CACHE_KEY,
        JSON.stringify({
          districts: districtsValue,
          locations: locationsValue,
          districtsSavedAt: Object.keys(districtsValue || {}).length ? Date.now() : current?.districtsSavedAt || 0,
          locationsSavedAt: Object.keys(locationsValue || {}).length ? Date.now() : current?.locationsSavedAt || 0,
        })
      );
    } catch {
      // Storage is optional; live data remains usable without it.
    }
  }, []);

  const readWeatherCache = useCallback(() => {
    try {
      const cached = JSON.parse(localStorage.getItem(WEATHER_CACHE_KEY) || "null");
      return cached && typeof cached === "object" ? cached : null;
    } catch {
      return null;
    }
  }, []);

  const syncDistrictMl = useCallback(async (districtList, { force = false } = {}) => {
    if (mlSyncInFlightRef.current) return;
    const now = Date.now();
    if (!force && now - lastMlRequestAtRef.current < ML_REQUEST_GAP_MS) return;

    const tasks = (districtList || []).filter(
      (district) =>
        toFiniteNumber(district.lat) !== null && toFiniteNumber(district.lng) !== null
    );
    if (!tasks.length) return;

    mlSyncInFlightRef.current = true;
    lastMlRequestAtRef.current = now;
    setMlStatus("loading");

    const persistentCache = readPersistentPredictionCache(
      FLOOD_ML_CACHE_KEY,
      ML_CACHE_TTL_MS
    );

    const cachedResults = {};
    tasks.forEach((district) => {
      const cached = persistentCache.items[district.id];
      if (!cached?.prediction || !isTrustedV63Prediction(cached.prediction)) return;
      if (getLiveRiskScore(cached.prediction) === null) return;
      cachedResults[district.id] = { ...cached.prediction, _lastKnown: true };
    });

    const tasksToFetch = force
      ? tasks
      : tasks.filter((district) => !cachedResults[district.id]);

    if (!force && Object.keys(cachedResults).length) {
      setBaseDistricts((current) => mergeDistrictMl(current, cachedResults));
      setMlStatus("live");
    }

    if (!tasksToFetch.length) {
      mlSyncInFlightRef.current = false;
      setMlStatus(Object.keys(cachedResults).length ? "live" : "unavailable");
      return;
    }

    const fetchMl = async (district) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), ML_FETCH_TIMEOUT_MS);
      try {
        const response = await fetch(`${API_BASE_URL}/api/ml/predict-risk`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            latitude: Number(district.lat),
            longitude: Number(district.lng),
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const message = await response.text();
          throw new Error(`ML ${response.status}: ${message}`);
        }

        const prediction = await response.json();
        if (!isTrustedV63Prediction(prediction)) {
          throw new Error(
            `Untrusted ML response for ${district.name}: expected real-data-v6.3 predictor metadata.`
          );
        }
        if (getLiveRiskScore(prediction) === null) {
          throw new Error(`V6.3 ML response for ${district.name} has no flood probability.`);
        }
        return prediction;
      } catch (error) {
        if (error?.name === "AbortError") {
          throw new Error(`Flood ML request timed out for ${district.name}.`);
        }
        throw error;
      } finally {
        clearTimeout(timer);
      }
    };

    try {
      const cacheItems = { ...(persistentCache.items || {}) };
      let cursor = 0;
      let successCount = 0;

      const worker = async () => {
        while (cursor < tasksToFetch.length) {
          const index = cursor++;
          const district = tasksToFetch[index];
          try {
            const prediction = await fetchMl(district);
            const updatedAt = extractPredictionTimestamp(prediction) || new Date().toISOString();
            const cacheEntry = { prediction, updatedAt };
            mlPredictionCacheRef.current.set(district.id, cacheEntry);
            cacheItems[district.id] = cacheEntry;
            successCount += 1;

            // Push each completed district into the UI immediately.
            setBaseDistricts((current) =>
              mergeDistrictMl(current, { [district.id]: prediction })
            );
            setMlStatus("live");
          } catch (error) {
            const cached = mlPredictionCacheRef.current.get(district.id);
            if (cached?.prediction) {
              setBaseDistricts((current) =>
                mergeDistrictMl(current, {
                  [district.id]: { ...cached.prediction, _lastKnown: true },
                })
              );
              setMlStatus("live");
            }
            console.warn(`ML unavailable for ${district.name}:`, error?.message || error);
          }
        }
      };

      await Promise.all(
        Array.from({ length: Math.min(ML_CONCURRENCY, tasksToFetch.length) }, () => worker())
      );

      if (Object.keys(cacheItems).length) {
        writePersistentPredictionCache(FLOOD_ML_CACHE_KEY, cacheItems);
      }
      if (tasksToFetch.length > successCount) {
        // Do not leave failed districts unavailable for the full 10-minute gap.
        // The next normal dashboard refresh can retry failed live calls.
        lastMlRequestAtRef.current = Date.now() - ML_REQUEST_GAP_MS + 55_000;
      }

      if (successCount === 0 && !Object.keys(cacheItems).length) {
        setMlStatus("unavailable");
      }
    } finally {
      mlSyncInFlightRef.current = false;
    }
  }, []);

  const syncLandslideMl = useCallback(async (districtList, { force = false } = {}) => {
    if (landslideSyncInFlightRef.current) return;
    const now = Date.now();
    if (!force && now - lastLandslideRequestAtRef.current < LANDSLIDE_ML_REQUEST_GAP_MS) return;

    const tasks = (districtList || []).filter(
      (district) =>
        toFiniteNumber(district.lat) !== null && toFiniteNumber(district.lng) !== null
    );
    if (!tasks.length) return;

    landslideSyncInFlightRef.current = true;
    lastLandslideRequestAtRef.current = now;
    setLandslideStatus("loading");

    const persistentCache = readPersistentPredictionCache(
      LANDSLIDE_ML_CACHE_KEY,
      LANDSLIDE_ML_CACHE_TTL_MS
    );

    const cachedResults = {};
    tasks.forEach((district) => {
      const cached = persistentCache.items[district.id];
      if (!cached?.prediction || !isTrustedLandslidePrediction(cached.prediction)) return;
      if (getLandslideRiskScore(cached.prediction) === null) return;
      cachedResults[district.id] = { ...cached.prediction, _lastKnown: true };
    });

    const tasksToFetch = force
      ? tasks
      : tasks.filter((district) => !cachedResults[district.id]);

    if (!force && Object.keys(cachedResults).length) {
      setBaseDistricts((current) =>
        mergeDistrictLandslideMl(current, cachedResults)
      );
      setLandslideStatus("live");
    }

    if (!tasksToFetch.length) {
      landslideSyncInFlightRef.current = false;
      setLandslideStatus(Object.keys(cachedResults).length ? "live" : "unavailable");
      return;
    }

    const fetchLandslide = async (district) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), ML_FETCH_TIMEOUT_MS);
      try {
        const response = await fetch(`${API_BASE_URL}/api/ml/predict-landslide`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            latitude: Number(district.lat),
            longitude: Number(district.lng),
          }),
          signal: controller.signal,
        });
        if (!response.ok) {
          const message = await response.text();
          throw new Error(`Landslide ML ${response.status}: ${message}`);
        }
        const prediction = await response.json();
        if (!isTrustedLandslidePrediction(prediction)) {
          throw new Error(`Untrusted landslide response for ${district.name}.`);
        }
        if (getLandslideRiskScore(prediction) === null) {
          throw new Error(`Landslide response for ${district.name} has no valid probability.`);
        }
        return prediction;
      } catch (error) {
        if (error?.name === "AbortError") {
          throw new Error(`Landslide ML request timed out for ${district.name}.`);
        }
        throw error;
      } finally {
        clearTimeout(timer);
      }
    };

    try {
      const cacheItems = { ...(persistentCache.items || {}) };
      let cursor = 0;
      let successCount = 0;

      const worker = async () => {
        while (cursor < tasksToFetch.length) {
          const index = cursor++;
          const district = tasksToFetch[index];
          try {
            const prediction = await fetchLandslide(district);
            const updatedAt = extractLandslidePredictionTimestamp(prediction) || new Date().toISOString();
            const cacheEntry = { prediction, updatedAt };
            landslidePredictionCacheRef.current.set(district.id, cacheEntry);
            cacheItems[district.id] = cacheEntry;
            successCount += 1;

            // Push each completed district into the UI immediately.
            setBaseDistricts((current) =>
              mergeDistrictLandslideMl(current, { [district.id]: prediction })
            );
            setLandslideStatus("live");
          } catch (error) {
            const cached = landslidePredictionCacheRef.current.get(district.id);
            if (cached?.prediction) {
              setBaseDistricts((current) =>
                mergeDistrictLandslideMl(current, {
                  [district.id]: { ...cached.prediction, _lastKnown: true },
                })
              );
              setLandslideStatus("live");
            }
            console.warn(`Landslide ML unavailable for ${district.name}:`, error?.message || error);
          }
        }
      };

      await Promise.all(
        Array.from(
          { length: Math.min(LANDSLIDE_ML_CONCURRENCY, tasksToFetch.length) },
          () => worker()
        )
      );

      if (Object.keys(cacheItems).length) {
        writePersistentPredictionCache(LANDSLIDE_ML_CACHE_KEY, cacheItems);
      }
      if (tasksToFetch.length > successCount) {
        // Retry failed live locations sooner than the standard 15-minute gap.
        lastLandslideRequestAtRef.current = Date.now() - LANDSLIDE_ML_REQUEST_GAP_MS + 55_000;
      }

      if (successCount === 0 && !Object.keys(cacheItems).length) {
        setLandslideStatus("unavailable");
      }
    } finally {
      landslideSyncInFlightRef.current = false;
    }
  }, []);

  const requestLocationMl = useCallback(async (location, district) => {
    if (!location || !district) return;
    const cacheId = `${district.id}::${location.id}`;
    const existingTime = location.mlUpdatedAt ? new Date(location.mlUpdatedAt).getTime() : 0;
    if (location.mlPrediction && existingTime && Date.now() - existingTime < ML_REQUEST_GAP_MS) return;
    if (locationFloodInFlightRef.current.has(cacheId)) return;

    const cached = locationFloodPredictionCacheRef.current.get(cacheId);
    if (
      isFreshPredictionCacheEntry(cached, ML_CACHE_TTL_MS) &&
      isTrustedV63Prediction(cached.prediction) &&
      getLiveRiskScore(cached.prediction) !== null
    ) {
      const prediction = cached.prediction;
      const updatedAt = cached.updatedAt;
      setBaseDistricts((current) => current.map((item) => item.id !== district.id ? item : {
        ...item,
        locations: (item.locations || []).map((candidate) => candidate.id !== location.id ? candidate : {
          ...candidate,
          mlPrediction: prediction,
          mlUpdatedAt: updatedAt,
          riskSource: "ML",
          score: getLiveRiskScore(prediction),
          risk: getLiveRiskLevel(prediction),
        }),
      }));
      return;
    }

    locationFloodInFlightRef.current.add(cacheId);
    setLocationMlLoadingByKey((current) => ({ ...current, [`${cacheId}::flood`]: true }));
    try {
      const prediction = await runWithConcurrency(locationFloodQueueRef, LOCATION_ML_CONCURRENCY, async () => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), ML_FETCH_TIMEOUT_MS);
        try {
          const response = await fetch(`${API_BASE_URL}/api/ml/predict-risk`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify({ latitude: Number(location.lat), longitude: Number(location.lng) }),
            signal: controller.signal,
          });
          if (!response.ok) {
            const message = await response.text();
            throw new Error(`ML ${response.status}: ${message}`);
          }
          const value = await response.json();
          if (!isTrustedV63Prediction(value)) throw new Error(`Untrusted V6.3 ML response for ${location.name}.`);
          if (getLiveRiskScore(value) === null) throw new Error(`No valid flood probability for ${location.name}.`);
          return value;
        } catch (error) {
          if (error?.name === "AbortError") throw new Error(`Flood ML timed out for ${location.name}.`);
          throw error;
        } finally {
          clearTimeout(timer);
        }
      });

      const updatedAt = extractPredictionTimestamp(prediction) || new Date().toISOString();
      locationFloodPredictionCacheRef.current.set(cacheId, { prediction, updatedAt });
      writePersistentPredictionCache(LOCATION_FLOOD_ML_CACHE_KEY, mapToCacheItems(locationFloodPredictionCacheRef.current));
      // Keep district-centroid scores separate from this actual locality-coordinate prediction.
      setBaseDistricts((current) => current.map((item) => item.id !== district.id ? item : {
        ...item,
        locations: (item.locations || []).map((candidate) => candidate.id !== location.id ? candidate : {
          ...candidate,
          mlPrediction: prediction,
          mlUpdatedAt: updatedAt,
          riskSource: "ML",
          score: getLiveRiskScore(prediction),
          risk: getLiveRiskLevel(prediction),
        }),
      }));
    } catch (error) {
      console.warn(`Location Flood ML unavailable for ${location.name}:`, error?.message || error);
    } finally {
      locationFloodInFlightRef.current.delete(cacheId);
      setLocationMlLoadingByKey((current) => {
        const next = { ...current };
        delete next[`${cacheId}::flood`];
        return next;
      });
    }
  }, []);

  const requestLocationLandslideMl = useCallback(async (location, district) => {
    if (!location || !district) return;
    const cacheId = `${district.id}::${location.id}`;
    const existingTime = location.landslideUpdatedAt ? new Date(location.landslideUpdatedAt).getTime() : 0;
    if (location.landslidePrediction && existingTime && Date.now() - existingTime < LANDSLIDE_ML_REQUEST_GAP_MS) return;
    if (locationLandslideInFlightRef.current.has(cacheId)) return;

    const cached = locationLandslidePredictionCacheRef.current.get(cacheId);
    if (
      isFreshPredictionCacheEntry(cached, LANDSLIDE_ML_CACHE_TTL_MS) &&
      isTrustedLandslidePrediction(cached.prediction) &&
      getLandslideRiskScore(cached.prediction) !== null
    ) {
      const prediction = cached.prediction;
      const updatedAt = cached.updatedAt;
      setBaseDistricts((current) => current.map((item) => item.id !== district.id ? item : {
        ...item,
        locations: (item.locations || []).map((candidate) => candidate.id !== location.id ? candidate : {
          ...candidate,
          landslideScore: getLandslideRiskScore(prediction),
          landslideRisk: getLandslideRiskLevel(prediction),
          landslideRiskSource: "ML",
          landslidePrediction: prediction,
          landslideUpdatedAt: updatedAt,
        }),
      }));
      return;
    }

    locationLandslideInFlightRef.current.add(cacheId);
    setLocationMlLoadingByKey((current) => ({ ...current, [`${cacheId}::landslide`]: true }));
    try {
      const prediction = await runWithConcurrency(locationLandslideQueueRef, LOCATION_ML_CONCURRENCY, async () => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), ML_FETCH_TIMEOUT_MS);
        try {
          const response = await fetch(`${API_BASE_URL}/api/ml/predict-landslide`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify({ latitude: Number(location.lat), longitude: Number(location.lng) }),
            signal: controller.signal,
          });
          if (!response.ok) {
            const message = await response.text();
            throw new Error(`Landslide ML ${response.status}: ${message}`);
          }
          const value = await response.json();
          if (!isTrustedLandslidePrediction(value)) throw new Error(`Untrusted landslide response for ${location.name}.`);
          if (getLandslideRiskScore(value) === null || !getLandslideRiskLevel(value)) throw new Error(`No valid landslide score for ${location.name}.`);
          return value;
        } catch (error) {
          if (error?.name === "AbortError") throw new Error(`Landslide ML timed out for ${location.name}.`);
          throw error;
        } finally {
          clearTimeout(timer);
        }
      });

      const updatedAt = extractLandslidePredictionTimestamp(prediction) || new Date().toISOString();
      locationLandslidePredictionCacheRef.current.set(cacheId, { prediction, updatedAt });
      writePersistentPredictionCache(LOCATION_LANDSLIDE_ML_CACHE_KEY, mapToCacheItems(locationLandslidePredictionCacheRef.current));
      setBaseDistricts((current) => current.map((item) => item.id !== district.id ? item : {
        ...item,
        locations: (item.locations || []).map((candidate) => candidate.id !== location.id ? candidate : {
          ...candidate,
          landslideScore: getLandslideRiskScore(prediction),
          landslideRisk: getLandslideRiskLevel(prediction),
          landslideRiskSource: "ML",
          landslidePrediction: prediction,
          landslideUpdatedAt: updatedAt,
        }),
      }));
    } catch (error) {
      console.warn(`Location Landslide ML unavailable for ${location.name}:`, error?.message || error);
    } finally {
      locationLandslideInFlightRef.current.delete(cacheId);
      setLocationMlLoadingByKey((current) => {
        const next = { ...current };
        delete next[`${cacheId}::landslide`];
        return next;
      });
    }
  }, []);

  const loadWeather = useCallback(
    async (districtList, { force = false } = {}) => {
      if (weatherSyncInFlightRef.current) return;
      const nowRequest = Date.now();
      if (!force && nowRequest - lastWeatherRequestAtRef.current < WEATHER_REQUEST_GAP_MS) {
        return;
      }

      const list = (districtList || DISTRICTS).filter(
        (district) =>
          toFiniteNumber(district.lat) !== null && toFiniteNumber(district.lng) !== null
      );
      if (!list.length) return;

      weatherSyncInFlightRef.current = true;
      lastWeatherRequestAtRef.current = nowRequest;
      setWeatherStatus("loading");
      setWeatherError("");

      const latitudes = list.map((district) => Number(district.lat).toFixed(4)).join(",");
      const longitudes = list.map((district) => Number(district.lng).toFixed(4)).join(",");
      const url =
        `${API_BASE_URL}/api/weather/forecast` +
        `?latitude=${encodeURIComponent(latitudes)}` +
        `&longitude=${encodeURIComponent(longitudes)}` +
        `&current=temperature_2m,relative_humidity_2m,precipitation,rain,weather_code,wind_speed_10m` +
        `&hourly=rain,precipitation,precipitation_probability` +
        `&past_days=1&forecast_days=2&timezone=Asia%2FKolkata`;

      try {
        const payload = await fetchBackendWeather(url, "districts");
        const items = Array.isArray(payload) ? payload : [payload];
        const now = new Date();
        const next = {};

        list.forEach((district, index) => {
          const item = items[index];
          if (!item) return;
          next[district.id] = {
            current: buildCurrentWeather(item),
            latitude: Number(district.lat),
            longitude: Number(district.lng),
            timezone: item.timezone || "Asia/Kolkata",
            fetched_at: now.toISOString(),
            sourceStatus: "live",
          };
        });

        if (!Object.keys(next).length) throw new Error("Weather backend returned no district data.");

        setWeatherByDistrict((previous) => ({ ...previous, ...next }));
        setWeatherStatus("live");
        setWeatherError("");

        const cachedBeforeLocations = readWeatherCache();
        saveWeatherCache(next, cachedBeforeLocations?.locations || {});
      } catch (error) {
        const cached = readWeatherCache();
        const savedAt = Number(cached?.districtsSavedAt || 0);
        const age = savedAt ? Date.now() - savedAt : Infinity;
        const cachedDistricts = cached?.districts || {};

        if (Object.keys(cachedDistricts).length && age <= WEATHER_CACHE_TTL_MS) {
          const marked = Object.fromEntries(
            Object.entries(cachedDistricts).map(([id, value]) => [id, { ...value, sourceStatus: "cached" }])
          );
          setWeatherByDistrict((previous) => ({ ...previous, ...marked }));
          setWeatherStatus("cached");
          setWeatherError("");
        } else {
          setWeatherStatus(
            Object.keys(weatherByDistrictRef.current).length ? "last-known" : "unavailable"
          );
          setWeatherError(error?.message || "Unable to load live weather.");
        }
      } finally {
        weatherSyncInFlightRef.current = false;
      }
    },
    [fetchBackendWeather, readWeatherCache, saveWeatherCache]
  );

  const loadLocationWeather = useCallback(
    async (location) => {
      if (!location) return;
      if (locationWeatherById[location.id]) return;

      const url =
        `${API_BASE_URL}/api/weather/forecast` +
        `?latitude=${encodeURIComponent(Number(location.lat).toFixed(4))}` +
        `&longitude=${encodeURIComponent(Number(location.lng).toFixed(4))}` +
        `&current=temperature_2m,relative_humidity_2m,precipitation,rain,weather_code,wind_speed_10m` +
        `&hourly=rain,precipitation,precipitation_probability` +
        `&past_days=1&forecast_days=2&timezone=Asia%2FKolkata`;

      try {
        const payload = await fetchBackendWeather(url, `location ${location.name}`);
        const item = Array.isArray(payload) ? payload[0] : payload;
        if (!item) throw new Error("Location weather response was empty.");
        const value = {
          current: buildCurrentWeather(item),
          latitude: Number(location.lat),
          longitude: Number(location.lng),
          timezone: item.timezone || "Asia/Kolkata",
          fetched_at: new Date().toISOString(),
          sourceStatus: "live",
        };
        setLocationWeatherById((previous) => ({ ...previous, [location.id]: value }));

        const cached = readWeatherCache();
        saveWeatherCache(cached?.districts || weatherByDistrictRef.current, {
          ...(cached?.locations || {}),
          [location.id]: value,
        });
      } catch (error) {
        console.warn(`Location weather unavailable for ${location.name}:`, error?.message || error);
      }
    },
    [fetchBackendWeather, locationWeatherById, readWeatherCache, saveWeatherCache]
  );

  const refreshOfficialAlerts = useCallback(async () => {
    if (officialAlertSyncInFlightRef.current) return;
    officialAlertSyncInFlightRef.current = true;
    try {
      const live = await fetchOfficialAlerts();
      setAlerts(live);
      setOfficialAlertStatus(live.length ? "live" : "empty");
    } catch (error) {
      console.warn("Official alert feed unavailable:", error?.message || error);
      setOfficialAlertStatus((current) =>
        current === "live" || current === "empty" ? current : "unavailable"
      );
    } finally {
      officialAlertSyncInFlightRef.current = false;
    }
  }, []);

  const loadDashboard = useCallback(
    async (manual = false) => {
      if (manual) setRefreshing(true);

      void refreshOfficialAlerts();

      try {
        setApiStatus("loading");
        const timeoutRequest = (promise, timeoutMs = 5000) =>
          new Promise((resolve, reject) => {
            let settled = false;
            const timer = setTimeout(() => {
              if (settled) return;
              settled = true;
              reject(new Error("Backend request timeout"));
            }, timeoutMs);

            Promise.resolve(promise).then(
              (value) => {
                if (settled) return;
                settled = true;
                clearTimeout(timer);
                resolve(value);
              },
              (error) => {
                if (settled) return;
                settled = true;
                clearTimeout(timer);
                reject(error);
              }
            );
          });

        const [overviewResult, districtsResult] = await Promise.allSettled([
          timeoutRequest(dashboardApi.getOverview()),
          timeoutRequest(dashboardApi.getDistricts()),
        ]);

        if (overviewResult.status === "fulfilled") setOverview(overviewResult.value);

        const districtFeedOk = districtsResult.status === "fulfilled";
        if (districtFeedOk) {
          const normalized = normalizeDistrictFeed(districtsResult.value);

          // Preserve the last successful V6.3 ML result while the dashboard
          // refresh is fetching a new ML reading. Never import risk values
          // from the generic district feed.
          setBaseDistricts((current) =>
            normalized.map((district) => {
              const existing = current.find((item) => item.id === district.id);
              let merged = district;
              if (existing?.riskSource === "ML" && existing.risk && existing.mlPrediction) {
                merged = {
                  ...merged,
                  score: existing.score,
                  risk: existing.risk,
                  riskSource: "ML",
                  mlPrediction: existing.mlPrediction,
                  mlUpdatedAt: existing.mlUpdatedAt,
                  locations: existing.locations || merged.locations,
                };
              }
              if (existing?.landslideRiskSource === "ML" && existing.landslideRisk && existing.landslidePrediction) {
                merged = {
                  ...merged,
                  landslideScore: existing.landslideScore,
                  landslideRisk: existing.landslideRisk,
                  landslideRiskSource: "ML",
                  landslidePrediction: existing.landslidePrediction,
                  landslideUpdatedAt: existing.landslideUpdatedAt,
                  locations: existing.locations || merged.locations,
                };
              }
              return merged;
            })
          );
        } else {
          setBaseDistricts((current) => (current.length ? current : DISTRICTS.map((district) => ({ ...district }))));
        }

        const backendOkay = overviewResult.status === "fulfilled" || districtFeedOk;
        setApiStatus(backendOkay ? "live" : "unavailable");
        setApiError(backendOkay ? "" : "Dashboard backend unavailable.");
        setLastSync(new Date().toISOString());

        const listForLiveData = districtFeedOk
          ? normalizeDistrictFeed(districtsResult.value)
          : baseDistrictsRef.current;

        void loadWeather(listForLiveData);
        void syncDistrictMl(listForLiveData);
        void syncLandslideMl(listForLiveData, { force: manual });
      } catch (error) {
        console.warn("Dashboard backend sync failed:", error?.message || error);
        setApiStatus("unavailable");
        setApiError(error?.message || "Dashboard backend unavailable.");
        void loadWeather(baseDistrictsRef.current);
      } finally {
        if (manual) setRefreshing(false);
      }
    },
    [loadWeather, refreshOfficialAlerts, syncDistrictMl, syncLandslideMl]
  );

  useEffect(() => {
    void loadDashboard(false);
    const dashboardTimer = setInterval(() => void loadDashboard(false), DASHBOARD_REFRESH_MS);
    const alertTimer = setInterval(() => void refreshOfficialAlerts(), OFFICIAL_ALERT_REFRESH_MS);
    return () => {
      clearInterval(dashboardTimer);
      clearInterval(alertTimer);
    };
  }, [loadDashboard, refreshOfficialAlerts]);

  useEffect(() => {
    const handleClick = (event) => {
      if (searchRef.current && !searchRef.current.contains(event.target)) setSearchOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const computedMetrics = useMemo(() => {
    const mlDistricts = districts.filter((district) => district.riskSource === "ML" && district.risk);
    const riskRank = { LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4 };
    let highestRisk = null;
    let overallRiskScore = null;

    mlDistricts.forEach((district) => {
      const risk = normalizeRisk(district.risk);
      if (!risk) return;
      if (!highestRisk || riskRank[risk] > riskRank[highestRisk]) highestRisk = risk;
    });

    mlDistricts.forEach((district) => {
      if (normalizeRisk(district.risk) !== highestRisk) return;
      const score = toFiniteNumber(district.score);
      if (score !== null && (overallRiskScore === null || score > overallRiskScore)) overallRiskScore = score;
    });

    return {
      activeAlerts: new Set(alerts.map((alert) => alert.bulletinId || alert.id)).size,
      highRiskZones: mlDistricts.filter((district) => ["HIGH", "CRITICAL"].includes(normalizeRisk(district.risk))).length,
      monitoredLocations: districts.reduce((total, district) => total + 1 + (district.locations?.length || 0), 0),
      liveMlDistricts: mlDistricts.length,
      overallRisk: highestRisk,
      overallRiskScore,
    };
  }, [districts, alerts]);

  const weatherBulletins = useMemo(
    () => buildWeatherBulletins(districts, weatherByDistrict),
    [districts, weatherByDistrict]
  );

  const focusDistrict = useMemo(() => {
    if (selectedPlace) {
      const name = selectedPlace.type === "District" ? selectedPlace.name : selectedPlace.district;
      const found = districts.find((district) => district.name === name);
      if (found) return found;
    }
    return districts[0] || null;
  }, [districts, selectedPlace]);

  const combinedAlerts = useMemo(
    () => [...alerts, ...weatherBulletins].sort((a, b) => getSeverityWeight(b.severity) - getSeverityWeight(a.severity) || new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime()),
    [alerts, weatherBulletins]
  );

  const placeBoard = useMemo(
    () => buildPlaceBoard(districts, alerts, weatherByDistrict, locationWeatherById),
    [districts, alerts, weatherByDistrict, locationWeatherById]
  );

  const handleDistrictSelect = useCallback((district) => {
    setSelectedPlace({ type: "District", ...district });
    setActiveTab("Live Monitoring");
  }, []);

  const handlePrefetchLocations = useCallback(
    (visibleLocations) => {
      (visibleLocations || []).forEach(({ location, district }) => {
        void requestLocationMl(location, district);
        void requestLocationLandslideMl(location, district);
      });
    },
    [requestLocationMl, requestLocationLandslideMl]
  );

  const handleLocationSelect = useCallback(
    (location, district) => {
      const mergedLocation = { ...location };
      const selected = {
        type: "Location",
        ...mergedLocation,
        district: district.name,
      };
      setSelectedPlace(selected);
      setActiveTab("Live Monitoring");
      void loadLocationWeather(location);
      void requestLocationMl(location, district);
      void requestLocationLandslideMl(location, district);
    },
    [loadLocationWeather, requestLocationMl, requestLocationLandslideMl]
  );

  const handleAlertMapSelect = useCallback(
    (alert) => {
      if (!alert) return;
      let district = alert.district
        ? districts.find((item) => item.name.toLowerCase() === String(alert.district).toLowerCase())
        : null;

      if (!district) {
        const matches = resolveDistrictsFromText(
          [alert.title, alert.description, alert.area, alert.location].filter(Boolean).join(" ")
        );
        district = districts.find((item) => matches.includes(item.name)) || null;
      }

      if (district) {
        const location = (district.locations || []).find((item) => alertMentionsName(alert, item.name));
        if (location) handleLocationSelect(location, district);
        else handleDistrictSelect(district);
        setSelectedAlert(null);
        return;
      }

      setSelectedAlert(alert);
      setActiveTab("Live Monitoring");
    },
    [districts, handleDistrictSelect, handleLocationSelect]
  );

  const handleSearchSelect = useCallback((result) => {
    setSelectedPlace(result);
    setActiveTab("Live Monitoring");
    if (result.type === "Location") {
      const parent = baseDistrictsRef.current.find((district) => district.name === result.district);
      if (parent) {
        void loadLocationWeather(result);
        void requestLocationMl(result, parent);
        void requestLocationLandslideMl(result, parent);
      }
    }
  }, [loadLocationWeather, requestLocationMl, requestLocationLandslideMl]);

  const handleAiAsk = useCallback(async () => {
    const query = aiQuery.trim();
    if (!query || isGenerating) return;

    try {
      setIsGenerating(true);
      const response = await aiApi.ask(query, selectedPlaceRef.current?.name || null);
      setAiResponse(response?.answer || response?.response || response?.message || "The AI service returned no answer.");
      setAiStatus("operational");
    } catch (error) {
      console.error("AI request failed:", error);
      setAiStatus("degraded");
      setAiResponse(
        error?.message === "SESSION_EXPIRED"
          ? "Your session has expired. Please sign in again."
          : "Unable to reach the Disaster Intelligence AI service. Check the FastAPI backend and AI configuration."
      );
    } finally {
      setIsGenerating(false);
    }
  }, [aiQuery, isGenerating]);

  const navigateTab = useCallback((tab) => {
    setActiveTab(tab);
    setMobileMenuOpen(false);
  }, []);

  const openRelief = useCallback(() => {
    window.open("https://disaster-app-drab.vercel.app/", "_blank", "noopener,noreferrer");
  }, []);

  const renderDashboard = () => {
    const weather = focusDistrict ? weatherByDistrict[focusDistrict.id] : null;
    const current = weather?.current || {};
    const trustedFocusPrediction =
      isTrustedV63Prediction(focusDistrict?.mlPrediction)
        ? focusDistrict.mlPrediction
        : null;
    const mlRisk = trustedFocusPrediction
      ? getLiveRiskLevel(trustedFocusPrediction)
      : null;
    const mlScore = trustedFocusPrediction
      ? getLiveRiskScore(trustedFocusPrediction)
      : null;
    const weatherSignal = getWeatherSignal(weather);
    const weatherStatusLabel =
      weatherStatus === "live"
        ? "LIVE"
        : weatherStatus === "cached" || weatherStatus === "last-known"
        ? "CACHED"
        : weatherStatus === "loading"
        ? "LOADING"
        : "OFFLINE";

    const cells = [
      { label: "Temperature", icon: Thermometer, value: toFiniteNumber(current.temperature) !== null ? `${Number(current.temperature).toFixed(1)}°C` : "--" },
      { label: "Rainfall · Today", icon: CloudRain, value: toFiniteNumber(current.today_rain) !== null ? `${Number(current.today_rain).toFixed(1)} mm` : "--" },
      { label: "Previous Day", icon: CloudRain, value: toFiniteNumber(current.previous_day_rain) !== null ? `${Number(current.previous_day_rain).toFixed(1)} mm` : "--" },
      { label: "Precipitation · Last Hour", icon: CloudRain, value: toFiniteNumber(current.rain) !== null ? `${Number(current.rain).toFixed(1)} mm` : "--" },
      { label: "Humidity", icon: CloudRain, value: toFiniteNumber(current.humidity) !== null ? `${Number(current.humidity).toFixed(0)}%` : "--" },
      { label: "Wind", icon: Navigation, value: toFiniteNumber(current.wind_speed) !== null ? `${Number(current.wind_speed).toFixed(1)} km/h` : "--" },
    ];

    return (
      <>
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
          <MetricCard icon={ShieldAlert} label="Live Alerts" value={officialAlertStatus === "loading" ? "—" : computedMetrics.activeAlerts} detail="Verified official events currently loaded" tone="red" onClick={() => setActiveTab("Live Monitoring")} />
          <MetricCard icon={AlertTriangle} label="High / Critical ML Zones" value={computedMetrics.highRiskZones} detail="Current flood-model risk only" tone="orange" onClick={() => setActiveTab("Risk Analytics")} />
          <MetricCard icon={MapPin} label="Locations Monitored" value={computedMetrics.monitoredLocations} detail="Configured districts and local locations" tone="sky" onClick={() => setActiveTab("Live Monitoring")} />
          <MetricCard icon={Activity} label="Platform Risk" value={computedMetrics.overallRisk || "—"} detail={computedMetrics.overallRiskScore !== null ? `Highest current ML score ${computedMetrics.overallRiskScore}%` : "No live ML score available"} tone="yellow" onClick={() => setActiveTab("Risk Analytics")} />
        </div>

        <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 shadow-xl">
          <SectionHeader
            title="Live Alert Center"
            subtitle="Official alerts and live weather signals are kept separate from ML predictions"
            icon={Bell}
            action={
              <span className="flex items-center gap-1.5 text-[9px] text-slate-400">
                <StatusDot active={officialAlertStatus === "live" || officialAlertStatus === "empty"} />
                {officialAlertStatus === "live" ? `${computedMetrics.activeAlerts} OFFICIAL ALERT${computedMetrics.activeAlerts === 1 ? "" : "S"}` : officialAlertStatus === "empty" ? "OFFICIAL FEED OPERATIONAL · NO ACTIVE ALERTS" : officialAlertStatus === "unavailable" ? "OFFICIAL FEED UNAVAILABLE" : "CHECKING OFFICIAL FEED"}
                {weatherBulletins.length > 0 && <span className="text-sky-400">· {weatherBulletins.length} WEATHER SIGNAL{weatherBulletins.length === 1 ? "" : "S"}</span>}
              </span>
            }
          />

          <div className="text-[9px] uppercase tracking-widest text-slate-600 mb-2">District-wise status · all 13 districts and configured locations</div>
          <DistrictAlertBoard rows={placeBoard} officialStatus={officialAlertStatus} onSelectDistrict={handleDistrictSelect} onSelectLocation={handleLocationSelect} />

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 mt-5 items-stretch">
            <div className="min-w-0">
              <div className="text-[9px] uppercase tracking-widest text-slate-600 mb-2">Official alerts</div>
              <AlertPanel alerts={alerts} onAlertClick={handleAlertMapSelect} />
            </div>
            <HazardAlertPanel districts={districts} alerts={alerts} onSelectDistrict={handleDistrictSelect} onSelectLocation={handleLocationSelect} />
          </div>
        </section>

        <div className="grid grid-cols-1 xl:grid-cols-[1.55fr_0.85fr] gap-4">
          <section className="rounded-2xl border border-slate-800/90 bg-slate-900/80 p-4 shadow-xl">
            <SectionHeader title="Live Risk Map" subtitle={selectedDisaster === "LANDSLIDE" ? "Uttarakhand geospatial landslide-risk intelligence" : "Uttarakhand geospatial flood-risk intelligence"} icon={Navigation} action={<button type="button" onClick={() => setActiveTab("Live Monitoring")} className="text-[10px] font-semibold text-sky-400 hover:text-sky-300 flex items-center gap-1">Open monitoring<ChevronRight className="w-3 h-3" /></button>} />

            <div className="flex flex-wrap gap-2 mb-3">
              {["ALL", "FLOOD", "LANDSLIDE", "EARTHQUAKE", "FIRE"].map((type) => {
                const enabled = type === "ALL" || type === "FLOOD" || type === "LANDSLIDE";
                return (
                  <button key={type} type="button" disabled={!enabled} onClick={() => enabled && setSelectedDisaster(type)} className={`px-3 py-1.5 rounded-lg border text-[9px] font-bold tracking-wider transition ${enabled ? selectedDisaster === type ? "border-sky-500/50 bg-sky-500/10 text-sky-300" : "border-slate-800 bg-slate-950/40 text-slate-500 hover:text-slate-300" : "border-slate-900 bg-slate-950/20 text-slate-700 cursor-not-allowed"}`}>
                    {type === "ALL" ? "ALL HAZARDS" : type}
                  </button>
                );
              })}
            </div>

            <div className="flex flex-wrap gap-2 mb-4">
              {["ALL", "LOW", "MEDIUM", "HIGH", "CRITICAL"].map((risk) => {
                const config = risk === "ALL" ? null : getRiskConfig(risk);
                return <button key={risk} type="button" onClick={() => setSelectedRisk(risk)} className={`px-2.5 py-1 rounded-md border text-[8px] font-bold uppercase tracking-wider ${selectedRisk === risk ? config ? `${config.border} ${config.text} bg-slate-900` : "border-sky-500/50 text-sky-300 bg-sky-500/10" : "border-slate-800 text-slate-600 bg-slate-950/30"}`}>{risk === "ALL" ? "ALL RISK" : risk}</button>;
              })}
            </div>

            <RiskMap districts={districts} selectedDisaster={selectedDisaster} selectedRisk={selectedRisk} onSelectDistrict={handleDistrictSelect} onSelectLocation={handleLocationSelect} onPrefetchLocations={handlePrefetchLocations} locationMlLoadingByKey={locationMlLoadingByKey} alerts={alerts} selectedPlace={selectedPlace} mapResetSignal={mapResetSignal} />

            {selectedPlace && (
              <div className="mt-3 rounded-xl border border-sky-500/20 bg-sky-500/[0.04] px-3 py-2.5 flex items-center justify-between">
                <div className="flex items-center gap-2"><MapPin className="w-3.5 h-3.5 text-sky-400" /><div><div className="text-[10px] font-semibold text-slate-300">Focused location</div><div className="text-xs text-sky-300">{selectedPlace.name}</div></div></div>
                <button type="button" onClick={() => { setSelectedPlace(null); setMapResetSignal((value) => value + 1); }} className="text-[9px] text-slate-600 hover:text-slate-300">Reset map</button>
              </div>
            )}
          </section>

          <div className="space-y-4">
            <section className="rounded-2xl border border-slate-800/90 bg-slate-900/80 p-4 shadow-xl">
              <SectionHeader title="System Status" subtitle="Platform health and data telemetry" icon={Radio} />
              <div className="grid grid-cols-2 gap-2">
                {[
                  ["API", apiStatus === "live", apiStatus === "live" ? "Operational" : apiStatus === "loading" ? "Checking" : "Unavailable"],
                  ["Weather", weatherStatus === "live", weatherStatus === "live" ? "Live Open-Meteo" : weatherStatus === "cached" || weatherStatus === "last-known" ? "Last-known real data" : weatherStatus === "loading" ? "Loading" : "Unavailable"],
                  ["Flood ML", mlStatus === "live", mlStatus === "live" ? "District predictions" : mlStatus === "loading" ? "Syncing" : mlStatus === "unavailable" ? "Unavailable" : "Waiting"],
                  ["Landslide ML", landslideStatus === "live", landslideStatus === "live" ? "District predictions" : landslideStatus === "loading" ? "Syncing" : landslideStatus === "unavailable" ? "Unavailable" : "Waiting"],
                  ["Official Alerts", officialAlertStatus === "live" || officialAlertStatus === "empty", officialAlertStatus === "live" ? "Live feed" : officialAlertStatus === "empty" ? "Operational · No active alerts" : officialAlertStatus === "unavailable" ? "Unavailable" : "Checking"],
                ].map(([name, active, status]) => (
                  <div key={name} className="rounded-xl border border-slate-800 bg-slate-950/30 p-3">
                    <div className="flex items-center gap-2"><StatusDot active={active === true} pulse={active === true && name !== "API"} /><span className="text-[10px] font-semibold text-slate-300">{name}</span></div>
                    <div className={`text-[9px] mt-2 ${active ? "text-emerald-400" : "text-red-400"}`}>{status}</div>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex items-center justify-between text-[9px] text-slate-600">
                <span>Last sync {lastSync ? new Date(lastSync).toLocaleTimeString() : "—"}</span>
                <button type="button" onClick={() => void loadDashboard(true)} className="text-sky-400 hover:text-sky-300 flex items-center gap-1"><RefreshCw className={`w-3 h-3 ${refreshing ? "animate-spin" : ""}`} />Sync</button>
              </div>
            </section>

            <section className="rounded-2xl border border-slate-800/90 bg-slate-900/80 p-4 shadow-xl">
              <SectionHeader title="Weather Telemetry" subtitle={focusDistrict ? focusDistrict.name : "Uttarakhand"} icon={CloudRain} action={<span className="text-[9px] text-slate-400">Open-Meteo</span>} />
              <div className="grid grid-cols-2 gap-3">
                {cells.map(({ label, icon: CellIcon, value }) => (
                  <div key={label} className="rounded-xl border border-slate-800 bg-slate-950/30 p-3">
                    <div className="flex items-center gap-2 text-slate-500"><CellIcon className="w-3.5 h-3.5" /><span className="text-[9px]">{label}</span></div>
                    <div className="text-xl font-bold text-slate-200 mt-2">{value}</div>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-800 bg-slate-950/30 px-3 py-2">
                <span className="text-[9px] text-slate-500">{focusDistrict?.name || "Uttarakhand"}{current.weather_code != null ? ` · Code ${current.weather_code}` : " · Weather unavailable"}</span>
                <span className="text-[9px] text-slate-500">Updated {formatRelativeTime(weather?.fetched_at)}</span>
                <span className="text-[9px] font-bold uppercase" style={{ color: weatherStatus === "live" ? "#22c55e" : "#64748b" }}>{weatherStatusLabel}</span>
              </div>
              {weatherSignal && <div className="mt-2 rounded-xl border border-yellow-500/20 bg-yellow-500/[0.04] px-3 py-2 text-[9px] text-yellow-400">Weather signal: {weatherSignal.text} · This is forecast telemetry, not ML risk.</div>}
              {weatherError && <div className="mt-2 text-[9px] text-red-400">{weatherError}</div>}

              <button type="button" onClick={() => setActiveTab("Risk Analytics")} className="w-full mt-3 rounded-xl border border-sky-500/20 bg-sky-500/[0.04] p-3 text-left hover:bg-sky-500/[0.08] transition">
                <div className="flex items-center justify-between"><span className="text-[10px] font-bold text-sky-400">FLOOD ML RISK</span><ChevronRight className="w-3.5 h-3.5 text-slate-600" /></div>
                <div className="text-xs text-slate-300 mt-1">{mlRisk ? `Current V6.3 flood-model output: ${getRiskConfig(mlRisk).label}${mlScore !== null ? ` · ${mlScore}%` : ""}.` : "Live V6.3 flood-model prediction is unavailable for this area; no weather heuristic or legacy risk value is used as a substitute."}</div>
              </button>
              <button type="button" onClick={() => setSelectedDisaster("LANDSLIDE")} className="w-full mt-3 rounded-xl border border-violet-500/20 bg-violet-500/[0.04] p-3 text-left hover:bg-violet-500/[0.08] transition">
                <div className="flex items-center justify-between"><span className="text-[10px] font-bold text-violet-300">LANDSLIDE ML RISK</span><ChevronRight className="w-3.5 h-3.5 text-slate-600" /></div>
                <div className="text-xs text-slate-300 mt-1">{focusDistrict?.landslideRiskSource === "ML" && focusDistrict?.landslideRisk ? `Current GSI landslide-model output: ${getRiskConfig(focusDistrict.landslideRisk).label}${focusDistrict.landslideScore !== null ? ` · ${focusDistrict.landslideScore}%` : ""}.` : "Live landslide-model prediction is unavailable for this area; no flood risk or weather heuristic is used as a substitute."}</div>
                <div className="mt-2 text-[8px] text-slate-600">GSI inventory + terrain DEM + NASA-trained model + live Open-Meteo weather</div>
              </button>
            </section>

            <section className="rounded-2xl border border-sky-500/10 bg-sky-500/[0.025] p-4 shadow-xl">
              <SectionHeader title="AI Intelligence" subtitle="Ask the disaster intelligence engine" icon={Zap} action={<button type="button" onClick={() => setActiveTab("AI Intelligence")} className="text-[9px] text-sky-400">Full AI</button>} />
              <div className="relative">
                <input value={aiQuery} onChange={(event) => setAiQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void handleAiAsk(); }} placeholder="Ask about floods, alerts, weather..." className="w-full h-10 rounded-xl border border-slate-800 bg-slate-950/50 px-3 pr-10 text-[10px] text-slate-300 placeholder:text-slate-700 outline-none focus:border-sky-500/40" />
                <button type="button" onClick={() => void handleAiAsk()} disabled={!aiQuery.trim() || isGenerating} className="absolute right-2 top-1/2 -translate-y-1/2 text-sky-400 disabled:text-slate-700"><Send className="w-3.5 h-3.5" /></button>
              </div>
            </section>
          </div>
        </div>
      </>
    );
  };

  const renderLiveMonitoring = () => (
    <>
      <section className="rounded-2xl border border-slate-800/90 bg-slate-900/80 p-4 shadow-xl">
        <SectionHeader title="Live Monitoring" subtitle="Real-time geospatial flood-risk monitoring" icon={Radio} action={<div className="flex items-center gap-2"><StatusDot active={weatherStatus === "live"} pulse={weatherStatus === "live"} /><span className="text-[9px] text-emerald-400">MONITORING {weatherStatus === "live" ? "ACTIVE" : "DEGRADED"}</span></div>} />
        <RiskMap districts={districts} selectedDisaster={selectedDisaster} selectedRisk={selectedRisk} onSelectDistrict={handleDistrictSelect} onSelectLocation={handleLocationSelect} onPrefetchLocations={handlePrefetchLocations} locationMlLoadingByKey={locationMlLoadingByKey} alerts={alerts} selectedPlace={selectedPlace} mapResetSignal={mapResetSignal} />
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
          <SectionHeader title="Monitored Regions" subtitle="Click a region to zoom into it" icon={MapPin} />
          <div className="space-y-2">
            {districts.map((district) => (
              <button key={district.id} type="button" onClick={() => handleDistrictSelect(district)} className="w-full flex items-center gap-3 p-3 rounded-xl border border-slate-800 bg-slate-950/20 hover:bg-slate-900/60 transition text-left">
                <div className="w-2 h-10 rounded-full" style={{ backgroundColor: district.riskSource === "ML" ? getRiskConfig(district.risk).color : "#475569" }} />
                <div className="flex-1 min-w-0"><div className="text-xs font-semibold text-slate-200">{district.name}</div><div className="text-[9px] text-slate-600 mt-1">{district.locations?.length || 0} configured locations · {district.alerts ?? "—"} official alerts</div></div>
                <RiskBadge risk={district.riskSource === "ML" ? district.risk : null} />
                <ChevronRight className="w-3.5 h-3.5 text-slate-700" />
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
          <SectionHeader title="Live Event Stream" subtitle="Official alerts and real weather signals" icon={Activity} />
          <DistrictAlertBoard rows={placeBoard} officialStatus={officialAlertStatus} onSelectDistrict={handleDistrictSelect} onSelectLocation={handleLocationSelect} />
          <div className="mt-5"><div className="text-[9px] uppercase tracking-widest text-slate-600 mb-2">Official alert feed</div><AlertPanel alerts={alerts} onAlertClick={handleAlertMapSelect} /></div>
        </section>
      </div>
    </>
  );

  const renderAnalytics = () => {
    // Ranking/distribution cards remain explicitly flood-specific. The Regional
    // Risk Analysis Graph below now plots both ML hazards independently.
    const liveDistricts = districts
      .filter((district) => district.riskSource === "ML" && Number.isFinite(Number(district.score)))
      .map((district) => ({ ...district, score: clamp(Number(district.score), 0, 100) }))
      .sort((a, b) => b.score - a.score);

    const distribution = [
      ["Low", "LOW"],
      ["Medium", "MEDIUM"],
      ["High", "HIGH"],
      ["Critical", "CRITICAL"],
    ].map(([name, key]) => ({
      name,
      key,
      value: liveDistricts.filter((district) => district.risk === key).length,
      color: getRiskConfig(key).color,
    }));

    // Use all 13 districts in their fixed geographic order, even while one of
    // the hazard models is still loading. Missing scores are shown as gaps.
    const graphDistricts = [...districts].sort(
      (a, b) => Number(a.order ?? 0) - Number(b.order ?? 0)
    );
    const graphWidth = 1000;
    const graphHeight = 270;
    const graphLeft = 34;
    const graphRight = 988;
    const graphTop = 18;
    const graphBottom = 236;
    const graphXRange = graphRight - graphLeft;
    const graphYRange = graphBottom - graphTop;
    const toGraphY = (score) => graphBottom - (score / 100) * graphYRange;

    const graphScoreFor = (district, hazard) => {
      const source = hazard === "flood" ? district.riskSource : district.landslideRiskSource;
      const rawScore = hazard === "flood" ? district.score : district.landslideScore;
      if (source !== "ML") return null;
      const score = toFiniteNumber(rawScore);
      return score === null ? null : clamp(score, 0, 100);
    };

    const graphSeriesDefinitions = [
      { key: "flood", label: "Flood ML", shortLabel: "Flood", color: "#38bdf8" },
      { key: "landslide", label: "Landslide ML", shortLabel: "Landslide", color: "#a78bfa" },
    ];

    const graphSeries = graphSeriesDefinitions.map((definition) => {
      const points = graphDistricts.map((district, index) => {
        const score = graphScoreFor(district, definition.key);
        const rawRisk = definition.key === "flood" ? district.risk : district.landslideRisk;
        const risk = score === null ? null : normalizeRisk(rawRisk) || riskFromScore(score);
        const x = graphDistricts.length === 1
          ? (graphLeft + graphRight) / 2
          : graphLeft + (index / (graphDistricts.length - 1)) * graphXRange;
        return {
          id: district.id,
          name: district.name,
          district,
          index,
          x,
          y: score === null ? null : toGraphY(score),
          score,
          risk,
        };
      });

      // Only calculate movement between adjacent districts when both actual
      // values are available. A missing model response is never treated as 0.
      const changes = points.slice(1).flatMap((point, index) => {
        const previous = points[index];
        if (point.score === null || previous.score === null) return [];
        const delta = Number((point.score - previous.score).toFixed(1));
        return [{
          from: previous,
          to: point,
          delta,
          midX: (previous.x + point.x) / 2,
          midY: (previous.y + point.y) / 2,
        }];
      });

      const validPoints = points.filter((point) => point.score !== null);
      const positiveChanges = changes.filter((item) => item.delta > 0);
      const negativeChanges = changes.filter((item) => item.delta < 0);
      const flatChanges = changes.filter((item) => item.delta === 0);
      const totalRise = positiveChanges.reduce((sum, item) => sum + item.delta, 0);
      const totalFall = Math.abs(negativeChanges.reduce((sum, item) => sum + item.delta, 0));
      const averageScore = validPoints.length
        ? validPoints.reduce((sum, point) => sum + point.score, 0) / validPoints.length
        : null;
      const scoreMin = validPoints.length ? Math.min(...validPoints.map((point) => point.score)) : null;
      const scoreMax = validPoints.length ? Math.max(...validPoints.map((point) => point.score)) : null;
      const scoreRange = scoreMin !== null && scoreMax !== null ? scoreMax - scoreMin : null;
      const standardDeviation = validPoints.length
        ? Math.sqrt(
            validPoints.reduce((sum, point) => sum + Math.pow(point.score - averageScore, 2), 0) /
              validPoints.length
          )
        : null;
      const largestRise = positiveChanges.length
        ? positiveChanges.reduce((best, item) => item.delta > best.delta ? item : best)
        : null;
      const largestFall = negativeChanges.length
        ? negativeChanges.reduce((best, item) => item.delta < best.delta ? item : best)
        : null;
      const criticalCount = validPoints.filter((point) => point.score >= 80).length;
      const highCount = validPoints.filter((point) => point.score >= 60 && point.score < 80).length;
      const mediumCount = validPoints.filter((point) => point.score >= 30 && point.score < 60).length;
      const lowCount = validPoints.filter((point) => point.score < 30).length;
      const bandChanges = changes.filter((item) => item.from.risk !== item.to.risk).length;
      const netChange = validPoints.length > 1
        ? validPoints[validPoints.length - 1].score - validPoints[0].score
        : null;

      return {
        ...definition,
        points,
        changes,
        stats: {
          validCount: validPoints.length,
          positiveChanges,
          negativeChanges,
          flatChanges,
          totalRise,
          totalFall,
          averageScore,
          scoreMin,
          scoreMax,
          scoreRange,
          standardDeviation,
          largestRise,
          largestFall,
          criticalCount,
          highCount,
          mediumCount,
          lowCount,
          bandChanges,
          netChange,
        },
      };
    });

    const floodSeries = graphSeries.find((series) => series.key === "flood");
    const landslideSeries = graphSeries.find((series) => series.key === "landslide");
    const hasGraphData = graphSeries.some((series) => series.points.some((point) => point.score !== null));

    const thresholdLines = [
      { score: 80, label: "CRITICAL", color: RISK_CONFIG.CRITICAL.color },
      { score: 60, label: "HIGH", color: RISK_CONFIG.HIGH.color },
      { score: 30, label: "MEDIUM", color: RISK_CONFIG.MEDIUM.color },
    ];

    const metricCards = [
      { key: "mean", label: "Mean", value: (stats) => stats.averageScore === null ? "—" : `${stats.averageScore.toFixed(1)}%` },
      { key: "range", label: "Range", value: (stats) => stats.scoreRange === null ? "—" : `${stats.scoreRange.toFixed(1)} pts` },
      { key: "stddev", label: "Std. Dev.", value: (stats) => stats.standardDeviation === null ? "—" : `${stats.standardDeviation.toFixed(1)} pts` },
      { key: "net", label: "Net Δ", value: (stats) => stats.netChange === null ? "—" : `${stats.netChange > 0 ? "+" : ""}${stats.netChange.toFixed(1)} pts` },
      { key: "rising", label: "Rising Segments", value: (stats) => `↑ ${stats.positiveChanges.length}` },
      { key: "falling", label: "Falling Segments", value: (stats) => `↓ ${stats.negativeChanges.length}` },
      { key: "total", label: "Total Rise / Fall", value: (stats) => `+${stats.totalRise.toFixed(1)} / −${stats.totalFall.toFixed(1)}` },
      { key: "bands", label: "Band Changes", value: (stats) => String(stats.bandChanges) },
    ];

    const scoreLabel = (score) => score === null ? "—" : `${score}%`;
    const riskLabel = (risk) => risk ? getRiskConfig(risk).label : "Unavailable";
    const formatDelta = (value) => value === null ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(1)}`;

    return (
      <>
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
          <MetricCard icon={ShieldAlert} label="Platform Risk" value={computedMetrics.overallRisk || "—"} detail={computedMetrics.overallRiskScore !== null ? `Current score ${computedMetrics.overallRiskScore}%` : "No ML score available"} tone="red" />
          <MetricCard icon={TrendingUp} label="Highest Flood ML Score" value={liveDistricts[0] ? `${liveDistricts[0].score}%` : "—"} detail={liveDistricts[0]?.name || "No flood ML data"} tone="orange" />
          <MetricCard icon={Activity} label="Data Freshness" value={weatherStatus === "live" ? "LIVE" : weatherStatus === "cached" ? "CACHED" : "—"} detail="Open-Meteo weather + flood ML" tone="emerald" />
          <MetricCard icon={Users} label="Flood ML Coverage" value={`${computedMetrics.liveMlDistricts}/13`} detail="Districts with successful flood-model output" tone="sky" />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
            <SectionHeader title="Live Flood Risk Distribution" subtitle="Only successful current flood-model predictions" icon={TrendingUp} />
            <div className="space-y-5">
              {distribution.map((item) => {
                const percentage = liveDistricts.length ? Math.round((item.value / liveDistricts.length) * 100) : 0;
                return <div key={item.key}><div className="flex items-center justify-between mb-2"><span className="text-[10px] text-slate-400">{item.name}</span><span className="text-[10px] font-bold" style={{ color: item.color }}>{item.value} districts · {percentage}%</span></div><div className="h-2 rounded-full bg-slate-950 overflow-hidden"><div className="h-full rounded-full transition-all duration-700" style={{ width: `${percentage}%`, backgroundColor: item.color }} /></div></div>;
              })}
            </div>
          </section>

          <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
            <SectionHeader title="Live Flood Risk Ranking" subtitle="Highest current flood-model scores" icon={MapPin} />
            <div className="space-y-2">
              {liveDistricts.slice(0, 7).map((district, index) => {
                const config = getRiskConfig(district.risk);
                return <button key={district.id} type="button" onClick={() => handleDistrictSelect(district)} className="w-full flex items-center gap-3 p-3 rounded-xl bg-slate-950/30 hover:bg-slate-900/70 transition"><span className="text-[10px] text-slate-700 w-4">{String(index + 1).padStart(2, "0")}</span><div className="flex-1 text-left"><div className="text-xs font-semibold text-slate-300">{district.name}</div><div className="mt-1 h-1 rounded-full bg-slate-900 overflow-hidden"><div className="h-full rounded-full" style={{ width: `${district.score}%`, backgroundColor: config.color }} /></div></div><span className="text-xs font-black" style={{ color: config.color }}>{district.score}%</span></button>;
              })}
              {!liveDistricts.length && <div className="text-xs text-slate-600 text-center py-6">Waiting for live flood-model data...</div>}
            </div>
          </section>
        </div>

        <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
          <SectionHeader
            title="Regional Risk Analysis Graph"
            subtitle="13 districts · fixed regional order · Flood and Landslide ML scores"
            icon={Activity}
            action={(
              <div className="flex flex-wrap items-center justify-end gap-3 text-[9px]">
                <span className="flex items-center gap-1.5" style={{ color: floodSeries.color }}><StatusDot active={mlStatus === "live"} pulse={mlStatus === "live"} />FLOOD {mlStatus === "live" ? "LIVE" : String(mlStatus).toUpperCase()}</span>
                <span className="flex items-center gap-1.5" style={{ color: landslideSeries.color }}><StatusDot active={landslideStatus === "live"} pulse={landslideStatus === "live"} />LANDSLIDE {landslideStatus === "live" ? "LIVE" : String(landslideStatus).toUpperCase()}</span>
              </div>
            )}
          />

          <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-[10px] text-slate-400">
            {graphSeries.map((series) => (
              <span key={series.key} className="inline-flex items-center gap-2">
                <span className="inline-block h-0.5 w-7 rounded-full" style={{ backgroundColor: series.color }} />
                <span style={{ color: series.color }}>{series.label}</span>
                <span className="text-slate-600">{series.stats.validCount}/13 districts</span>
              </span>
            ))}
            <span className="text-slate-600">Missing model values stay blank; they are never plotted as zero.</span>
          </div>

          <div className="mb-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
            {metricCards.map((metric) => (
              <div key={metric.key} className="rounded-lg border border-slate-800 bg-slate-950/30 px-3 py-2">
                <div className="text-[8px] uppercase tracking-wider text-slate-600">{metric.label}</div>
                {graphSeries.map((series) => (
                  <div key={series.key} className="mt-1 flex items-center justify-between gap-2 text-[9px]">
                    <span style={{ color: series.color }}>{series.shortLabel}</span>
                    <span className="font-bold text-slate-200 text-right">{metric.value(series.stats)}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-950 relative overflow-hidden p-3">
            <div className="absolute inset-0 opacity-20 bg-[linear-gradient(to_right,#334155_1px,transparent_1px),linear-gradient(to_bottom,#334155_1px,transparent_1px)] [background-size:40px_40px]" />
            {hasGraphData ? (
              <svg viewBox={`0 0 ${graphWidth} ${graphHeight}`} preserveAspectRatio="none" className="relative w-full h-[340px]" role="img" aria-label="Flood and landslide ML risk scores for each Uttarakhand district">
                <rect x={graphLeft} y={graphTop} width={graphXRange} height={toGraphY(80) - graphTop} fill={RISK_CONFIG.CRITICAL.color} fillOpacity="0.045" />
                <rect x={graphLeft} y={toGraphY(80)} width={graphXRange} height={toGraphY(60) - toGraphY(80)} fill={RISK_CONFIG.HIGH.color} fillOpacity="0.035" />
                <rect x={graphLeft} y={toGraphY(60)} width={graphXRange} height={toGraphY(30) - toGraphY(60)} fill={RISK_CONFIG.MEDIUM.color} fillOpacity="0.025" />
                <rect x={graphLeft} y={toGraphY(30)} width={graphXRange} height={graphBottom - toGraphY(30)} fill={RISK_CONFIG.LOW.color} fillOpacity="0.02" />

                {[0, 20, 40, 60, 80, 100].map((score) => (
                  <g key={score}>
                    <line x1={graphLeft} y1={toGraphY(score)} x2={graphRight} y2={toGraphY(score)} stroke="#334155" strokeWidth="1" strokeDasharray={score === 0 || score === 100 ? "0" : "4 5"} opacity="0.6" />
                    <text x="5" y={toGraphY(score) + 4} fill="#64748b" fontSize="10">{score}</text>
                  </g>
                ))}

                {thresholdLines.map((threshold) => (
                  <g key={threshold.score}>
                    <line x1={graphLeft} y1={toGraphY(threshold.score)} x2={graphRight} y2={toGraphY(threshold.score)} stroke={threshold.color} strokeWidth="1.5" strokeDasharray="7 5" opacity="0.75" />
                    <text x={graphRight - 2} y={toGraphY(threshold.score) - 5} textAnchor="end" fill={threshold.color} fontSize="9" fontWeight="700">{threshold.score} · {threshold.label}</text>
                  </g>
                ))}

                {graphSeries.map((series) => (
                  <g key={series.key}>
                    {series.points.slice(1).map((point, index) => {
                      const previous = series.points[index];
                      if (point.score === null || previous.score === null) return null;
                      return <line key={`${series.key}-segment-${previous.id}-${point.id}`} x1={previous.x} y1={previous.y} x2={point.x} y2={point.y} stroke={series.color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" opacity="0.95" />;
                    })}
                    {series.points.filter((point) => point.score !== null).map((point) => {
                      const labelY = series.key === "flood"
                        ? clamp(point.y - 12, graphTop + 10, graphBottom - 5)
                        : clamp(point.y + 17, graphTop + 10, graphBottom - 2);
                      return (
                        <g key={`${series.key}-${point.id}`}>
                          <line x1={point.x} y1={graphBottom} x2={point.x} y2={point.y} stroke={series.color} strokeWidth="1" opacity="0.18" />
                          <circle cx={point.x} cy={point.y} r={series.key === "flood" ? 5.5 : 6} fill="#0d1420" stroke={series.color} strokeWidth="2.5" />
                          <circle cx={point.x} cy={point.y} r="2" fill={series.color} />
                          <text x={point.x} y={labelY} textAnchor="middle" fill={series.color} fontSize="9" fontWeight="800">{point.score}%</text>
                          <title>{`${series.label} · ${point.name}: ${point.score}% · ${riskLabel(point.risk)}`}</title>
                        </g>
                      );
                    })}
                  </g>
                ))}

                {graphDistricts.map((district, index) => {
                  const x = graphDistricts.length === 1
                    ? (graphLeft + graphRight) / 2
                    : graphLeft + (index / (graphDistricts.length - 1)) * graphXRange;
                  return <text key={`district-label-${district.id}`} x={x} y={graphBottom + 16} textAnchor="middle" fill="#94a3b8" fontSize="8">{district.name.length > 12 ? `${district.name.slice(0, 11)}…` : district.name}</text>;
                })}

                <text x="5" y={graphTop + 10} fill="#64748b" fontSize="9">RISK SCORE (%)</text>
                <text x={graphRight - 2} y={graphHeight - 4} textAnchor="end" fill="#64748b" fontSize="9">District order →</text>
              </svg>
            ) : (
              <div className="relative h-[340px] flex items-center justify-center text-xs text-slate-600">Waiting for Flood and Landslide ML data...</div>
            )}
          </div>

          <div className="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-2">
            {[
              { label: "CRITICAL ≥ 80", key: "criticalCount" },
              { label: "HIGH 60–79", key: "highCount" },
              { label: "MEDIUM 30–59", key: "mediumCount" },
              { label: "LOW < 30", key: "lowCount" },
            ].map((band) => (
              <div key={band.key} className="rounded-lg border border-slate-800 bg-slate-950/30 px-3 py-2">
                <span className="text-[9px] font-semibold" style={{ color: RISK_CONFIG[band.key === "criticalCount" ? "CRITICAL" : band.key === "highCount" ? "HIGH" : band.key === "mediumCount" ? "MEDIUM" : "LOW"].color }}>{band.label}</span>
                {graphSeries.map((series) => (
                  <div key={series.key} className="mt-1 flex items-center justify-between gap-2 text-[9px]">
                    <span style={{ color: series.color }}>{series.shortLabel}</span>
                    <span className="text-xs font-black text-slate-200">{series.stats[band.key]}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>

          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2 text-[9px]">
            {graphSeries.map((series) => (
              <div key={`${series.key}-rise`} className="rounded-lg border border-slate-800 bg-slate-950/30 px-3 py-2 text-slate-500">
                <div className="font-semibold mb-1" style={{ color: series.color }}>{series.label} · Largest rise</div>
                {series.stats.largestRise ? `${series.stats.largestRise.from.name} → ${series.stats.largestRise.to.name} (+${series.stats.largestRise.delta.toFixed(1)} pts)` : "No adjacent upward segment available"}
                <div className="mt-2 font-semibold" style={{ color: series.color }}>{series.label} · Largest fall</div>
                {series.stats.largestFall ? `${series.stats.largestFall.from.name} → ${series.stats.largestFall.to.name} (${series.stats.largestFall.delta.toFixed(1)} pts)` : "No adjacent downward segment available"}
              </div>
            ))}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-[9px] text-slate-600">
            {graphSeries.map((series) => (
              <span key={`${series.key}-movement`}>
                <span style={{ color: series.color }}>{series.shortLabel}:</span>{" "}
                ↑ {series.stats.positiveChanges.length} rising · ↓ {series.stats.negativeChanges.length} falling · → {series.stats.flatChanges.length} flat · Σ↑ {series.stats.totalRise.toFixed(1)} · Σ↓ {series.stats.totalFall.toFixed(1)} · Band transitions {series.stats.bandChanges}
              </span>
            ))}
            <span>Movement is calculated only between adjacent districts with valid scores for the same hazard.</span>
          </div>

          <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            {graphDistricts.map((district, index) => {
              const previous = graphDistricts[index - 1];
              const floodScore = graphScoreFor(district, "flood");
              const landslideScore = graphScoreFor(district, "landslide");
              const previousFloodScore = previous ? graphScoreFor(previous, "flood") : null;
              const previousLandslideScore = previous ? graphScoreFor(previous, "landslide") : null;
              const floodDelta = floodScore !== null && previousFloodScore !== null ? floodScore - previousFloodScore : null;
              const landslideDelta = landslideScore !== null && previousLandslideScore !== null ? landslideScore - previousLandslideScore : null;
              const floodRisk = floodScore === null ? null : normalizeRisk(district.risk) || riskFromScore(floodScore);
              const landslideRisk = landslideScore === null ? null : normalizeRisk(district.landslideRisk) || riskFromScore(landslideScore);
              return (
                <button key={district.id} type="button" onClick={() => handleDistrictSelect(district)} className="rounded-lg border border-slate-800 bg-slate-950/30 px-2.5 py-2 text-left hover:bg-slate-900/70 transition">
                  <div className="text-[9px] text-slate-300 font-semibold truncate">{district.name}</div>
                  <div className="mt-2 flex items-center justify-between gap-2 text-[9px]">
                    <span style={{ color: floodSeries.color }}>Flood</span>
                    <span className="font-black text-slate-200">{scoreLabel(floodScore)}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2 text-[8px]">
                    <span className="text-slate-600">{riskLabel(floodRisk)}</span>
                    <span className={floodDelta === null ? "text-slate-700" : floodDelta > 0 ? "text-orange-400" : floodDelta < 0 ? "text-emerald-400" : "text-slate-500"}>{formatDelta(floodDelta)}</span>
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-2 text-[9px]">
                    <span style={{ color: landslideSeries.color }}>Landslide</span>
                    <span className="font-black text-slate-200">{scoreLabel(landslideScore)}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2 text-[8px]">
                    <span className="text-slate-600">{riskLabel(landslideRisk)}</span>
                    <span className={landslideDelta === null ? "text-slate-700" : landslideDelta > 0 ? "text-orange-400" : landslideDelta < 0 ? "text-emerald-400" : "text-slate-500"}>{formatDelta(landslideDelta)}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      </>
    );
  };

  const renderAI = () => (
    <div className="max-w-5xl mx-auto h-[calc(100vh-190px)] min-h-[600px]">
      <AIWorkspace aiQuery={aiQuery} setAiQuery={setAiQuery} aiResponse={aiResponse} isGenerating={isGenerating} aiStatus={aiStatus} onAsk={() => void handleAiAsk()} />
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans">
      <header className="sticky top-0 z-[1200] border-b border-slate-800/80 bg-slate-950/95 backdrop-blur-xl">
        <div className="max-w-[1800px] mx-auto px-4 md:px-6 h-[68px] flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 shrink-0">
            <div className="relative w-10 h-10 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center"><Radio className="w-5 h-5 text-sky-400" /><span className="absolute -right-0.5 -top-0.5 w-2 h-2 rounded-full bg-emerald-400" /></div>
            <div className="hidden sm:block"><div className="text-sm font-black tracking-[0.14em] text-slate-100">DISASTER</div><div className="text-[9px] font-semibold tracking-[0.24em] text-sky-400">INTELLIGENCE</div></div>
          </div>

          <div ref={searchRef} className="relative flex-1 max-w-[520px] hidden md:block">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600" />
            <input value={searchQuery} onChange={(event) => { setSearchQuery(event.target.value); setSearchOpen(true); }} onFocus={() => setSearchOpen(true)} placeholder="Search district, locality or monitored area..." className="w-full h-10 rounded-xl border border-slate-800 bg-slate-950/60 pl-10 pr-20 text-xs text-slate-300 placeholder:text-slate-700 outline-none focus:border-sky-500/40" />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[8px] text-slate-700 border border-slate-800 rounded px-1.5 py-0.5">SEARCH</span>
            {searchOpen && searchQuery.trim() && <SearchPanel query={searchQuery} districts={districts} onSelect={handleSearchSelect} onClose={() => setSearchOpen(false)} />}
          </div>

          <div className="flex items-center gap-1.5">
            <button type="button" onClick={() => setNotificationsOpen((value) => !value)} className="relative w-9 h-9 rounded-lg hover:bg-slate-800 flex items-center justify-center text-slate-500 hover:text-slate-200 transition"><Bell className="w-4 h-4" />{combinedAlerts.length > 0 && <span className="absolute right-1.5 top-1.5 w-1.5 h-1.5 rounded-full bg-red-500" />}</button>
            <button type="button" onClick={() => setProfileOpen((value) => !value)} className="flex items-center gap-2 ml-1 pl-2 border-l border-slate-800"><div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center"><User className="w-4 h-4 text-slate-400" /></div><div className="hidden lg:block text-left"><div className="text-[10px] font-semibold text-slate-300 max-w-[110px] truncate">{user?.name || user?.username || "Operator"}</div><div className="text-[8px] text-emerald-400">AUTHENTICATED</div></div><ChevronDown className="hidden lg:block w-3 h-3 text-slate-700" /></button>
            <button type="button" onClick={() => setMobileMenuOpen((value) => !value)} className="md:hidden w-9 h-9 rounded-lg hover:bg-slate-800 flex items-center justify-center"><Menu className="w-4 h-4" /></button>
          </div>
        </div>

        <div className="hidden md:block border-t border-slate-800/60">
          <div className="max-w-[1800px] mx-auto px-4 md:px-6 h-11 flex items-center gap-1">
            {TAB_CONFIG.map((tab) => { const Icon = tab.icon; const active = activeTab === tab.id; return <button key={tab.id} type="button" onClick={() => tab.id === "Relief" ? openRelief() : navigateTab(tab.id)} className={`h-full px-4 flex items-center gap-2 text-[10px] font-semibold border-b-2 transition ${active ? "text-sky-300 border-sky-500" : "text-slate-600 border-transparent hover:text-slate-300"}`}><Icon className="w-3.5 h-3.5" />{tab.id}</button>; })}
            <div className="ml-auto flex items-center gap-2 text-[9px] text-slate-600"><StatusDot active={apiStatus === "live"} />{apiStatus === "live" ? "SYSTEM OPERATIONAL" : apiStatus === "loading" ? "SYSTEM CHECKING" : "SYSTEM DEGRADED"}</div>
          </div>
        </div>

        {mobileMenuOpen && <div className="md:hidden border-t border-slate-800 bg-slate-900 p-2">{TAB_CONFIG.map((tab) => { const Icon = tab.icon; return <button key={tab.id} type="button" onClick={() => { if (tab.id === "Relief") { openRelief(); setMobileMenuOpen(false); } else navigateTab(tab.id); }} className={`w-full px-3 py-3 rounded-lg flex items-center gap-3 text-xs ${activeTab === tab.id ? "bg-sky-500/10 text-sky-300" : "text-slate-500"}`}><Icon className="w-4 h-4" />{tab.id}</button>; })}</div>}

        {notificationsOpen && (
          <div className="absolute right-4 top-[62px] w-[340px] rounded-2xl border border-slate-800 bg-slate-900/98 shadow-2xl p-3">
            <div className="flex items-center justify-between px-2 pb-2"><span className="text-xs font-bold text-slate-200">Notifications</span><button type="button" onClick={() => setNotificationsOpen(false)} className="text-slate-600 hover:text-slate-300"><X className="w-3.5 h-3.5" /></button></div>
            <AlertPanel alerts={combinedAlerts.slice(0, 4)} onAlertClick={(alert) => { setNotificationsOpen(false); handleAlertMapSelect(alert); }} />
          </div>
        )}

        {profileOpen && (
          <div className="absolute right-4 top-[62px] w-64 rounded-2xl border border-slate-800 bg-slate-900/98 shadow-2xl p-3">
            <div className="p-3 border-b border-slate-800"><div className="text-xs font-semibold text-slate-200">{user?.name || user?.username || "Operator"}</div><div className="text-[10px] text-slate-600 mt-1">{user?.email || "Authenticated operator"}</div></div>
            <button type="button" onClick={logout} className="w-full mt-2 px-3 py-2.5 rounded-lg hover:bg-red-500/10 text-left text-[10px] text-red-400 flex items-center gap-2"><LogOut className="w-3.5 h-3.5" />Sign out</button>
          </div>
        )}
      </header>

      <main className="max-w-[1800px] mx-auto px-4 md:px-6 py-5">
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 mb-5">
          <div>
            <div className="flex items-center gap-2 mb-2"><StatusDot active={apiStatus === "live"} /><span className={`text-[9px] uppercase tracking-[0.2em] ${apiStatus === "live" ? "text-emerald-400" : "text-yellow-400"}`}>{apiStatus === "live" ? "System operational" : apiStatus === "loading" ? "System checking" : "System degraded"}</span></div>
            <h1 className="text-xl md:text-2xl font-black tracking-tight text-slate-100">Uttarakhand Disaster Intelligence</h1>
            <p className="text-[11px] text-slate-600 mt-1">Live monitoring, geospatial flood-risk analytics and AI-assisted disaster intelligence.</p>
          </div>
          <div className="flex items-center gap-2"><div className="hidden sm:flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/30 px-3 py-2"><RefreshCw className={`w-3.5 h-3.5 text-slate-600 ${refreshing ? "animate-spin" : ""}`} /><span className="text-[9px] text-slate-600">Sync {lastSync ? new Date(lastSync).toLocaleTimeString() : "—"}</span></div><button type="button" onClick={() => void loadDashboard(true)} className="h-9 px-3 rounded-xl border border-slate-800 bg-slate-950/40 hover:bg-slate-900 text-[10px] text-slate-400 flex items-center gap-2"><RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />Refresh</button></div>
        </div>

        {apiError && <div className="mb-4 rounded-xl border border-yellow-500/20 bg-yellow-500/[0.04] px-4 py-3 flex items-start gap-3"><AlertTriangle className="w-4 h-4 text-yellow-400 mt-0.5" /><div><div className="text-xs font-semibold text-yellow-300">Backend reconnecting</div><div className="text-[10px] text-slate-500 mt-1">{apiError}</div></div></div>}

        <div className="space-y-4">
          {activeTab === "Dashboard" && renderDashboard()}
          {activeTab === "Live Monitoring" && renderLiveMonitoring()}
          {activeTab === "Risk Analytics" && renderAnalytics()}
          {activeTab === "AI Intelligence" && renderAI()}
        </div>

        <footer className="mt-8 pt-4 border-t border-slate-900 flex flex-col sm:flex-row items-center justify-between gap-2"><div className="text-[9px] text-slate-700">DISASTER INTELLIGENCE • UTTARAKHAND</div><div className="flex items-center gap-3 text-[9px] text-slate-700"><span>React</span><span>•</span><span>FastAPI</span><span>•</span><span>Leaflet</span><span>•</span><span>Groq AI</span></div></footer>
      </main>

      {selectedAlert && (
        <div className="fixed inset-0 z-[2000] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-3"><AlertOctagon className="w-5 h-5 text-red-400" /><div><div className="text-xs font-bold text-slate-200">Alert Intelligence</div><div className="text-[9px] text-slate-600 mt-0.5">{getAlertArea(selectedAlert) || "Area not provided"}</div></div></div>
              <button type="button" onClick={() => setSelectedAlert(null)} className="text-slate-600 hover:text-slate-300"><X className="w-4 h-4" /></button>
            </div>
            <div className="p-5">
              <span className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-md border ${getAlertConfig(selectedAlert.severity).border} ${getAlertConfig(selectedAlert.severity).text} text-[9px] font-bold uppercase tracking-wider`}><span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: getAlertConfig(selectedAlert.severity).color }} />{selectedAlert.isBulletin ? "मौसम बुलेटिन" : getAlertConfig(selectedAlert.severity).label}</span>
              <h3 className="text-base font-bold text-slate-100 mt-4">{selectedAlert.title}</h3>
              <p className="text-xs leading-6 text-slate-500 mt-2">{selectedAlert.description || "No description provided by source."}</p>
              <div className="grid grid-cols-2 gap-3 mt-5"><div className="rounded-xl border border-slate-800 bg-slate-950/30 p-3"><div className="text-[9px] uppercase text-slate-600">Location</div><div className="text-xs text-slate-300 mt-1">{getAlertArea(selectedAlert) || "Not provided"}</div></div><div className="rounded-xl border border-slate-800 bg-slate-950/30 p-3"><div className="text-[9px] uppercase text-slate-600">Received</div><div className="text-xs text-slate-300 mt-1">{formatRelativeTime(selectedAlert.timestamp)}</div></div></div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3"><div className="rounded-xl border border-slate-800 bg-slate-950/30 p-3"><div className="text-[9px] uppercase text-slate-600">Source</div><div className="text-xs text-slate-300 mt-1">{selectedAlert.source || "Not provided"}</div></div><div className="rounded-xl border border-slate-800 bg-slate-950/30 p-3"><div className="text-[9px] uppercase text-slate-600">Valid until</div><div className="text-xs text-slate-300 mt-1">{selectedAlert.valid_until ? new Date(selectedAlert.valid_until).toLocaleString() : "Not provided"}</div></div></div>
              {selectedAlert.source_url && <a href={selectedAlert.source_url} target="_blank" rel="noreferrer" className="block text-[10px] text-sky-400 hover:text-sky-300 mt-4">View official source</a>}
              <button type="button" onClick={() => handleAlertMapSelect(selectedAlert)} className="w-full mt-4 h-10 rounded-xl bg-sky-600 hover:bg-sky-500 text-xs font-semibold flex items-center justify-center gap-2"><Crosshair className="w-3.5 h-3.5" />Locate on live map</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
