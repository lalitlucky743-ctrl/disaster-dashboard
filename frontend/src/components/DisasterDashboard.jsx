import React, {
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
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CloudRain,
  Droplets,
  Crosshair,
  Gauge,
  Layers,
  LogOut,
  MapPin,
  Maximize2,
  Menu,
  MessageSquareText,
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
  TrendingDown,
  Wind,
  TrendingUp,
  User,
  Users,
  X,
  Zap,
} from "lucide-react";

import {
  Circle,
  CircleMarker,
  MapContainer,
  Polygon,
  Popup,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";

import { dashboardApi } from "../api/dashboardApi";
import { aiApi } from "../api/aiApi";
import { useAuth } from "../context/AuthContext";

const API_BASE_URL =
  import.meta.env.VITE_API_URL ||
  "https://disaster-dashboard-9qr8.onrender.com";

/* =========================================================
   CONSTANTS
========================================================= */

const UTTARAKHAND_CENTER = [30.0668, 79.0193];

const DEFAULT_ZOOM = 7;

const TAB_CONFIG = [
  {
    id: "Dashboard",
    icon: Gauge,
  },
  {
    id: "Live Monitoring",
    icon: Radio,
  },
  {
    id: "Risk Analytics",
    icon: TrendingUp,
  },
  {
    id: "AI Intelligence",
    icon: MessageSquareText,
  },
];

const RISK_CONFIG = {
  LOW: {
    label: "Low",
    color: "#22c55e",
    bg: "bg-emerald-500",
    text: "text-emerald-400",
    border: "border-emerald-500/30",
    fill: "#22c55e",
  },

  MEDIUM: {
    label: "Medium",
    color: "#eab308",
    bg: "bg-yellow-500",
    text: "text-yellow-400",
    border: "border-yellow-500/30",
    fill: "#eab308",
  },

  HIGH: {
    label: "High",
    color: "#f97316",
    bg: "bg-orange-500",
    text: "text-orange-400",
    border: "border-orange-500/30",
    fill: "#f97316",
  },

  CRITICAL: {
    label: "Critical",
    color: "#ef4444",
    bg: "bg-red-500",
    text: "text-red-400",
    border: "border-red-500/30",
    fill: "#ef4444",
  },
};

/*
  Fallback geographical intelligence.

  Backend data will override this when available.
  These coordinates are intentionally kept in frontend
  only as a resilient UI fallback.
*/

const DISTRICTS = [
  {
    id: "almora",
    name: "Almora",
    lat: 29.5971,
    lng: 79.6591,
    risk: "HIGH",
    score: 78,
    alerts: 4,
    weather: "Heavy Rain",
    locations: [
      {
        id: "almora-city",
        name: "Almora City",
        lat: 29.5971,
        lng: 79.6591,
        risk: "HIGH",
        type: "Landslide",
      },
      {
        id: "kasar-devi",
        name: "Kasar Devi",
        lat: 29.6252,
        lng: 79.6661,
        risk: "CRITICAL",
        type: "Landslide",
      },
      {
        id: "binsar",
        name: "Binsar",
        lat: 29.6568,
        lng: 79.7554,
        risk: "HIGH",
        type: "Landslide",
      },
      {
        id: "jageshwar",
        name: "Jageshwar",
        lat: 29.6436,
        lng: 79.858,
        risk: "MEDIUM",
        type: "Heavy Rain",
      },
      {
        id: "ranikhet",
        name: "Ranikhet",
        lat: 29.6434,
        lng: 79.4322,
        risk: "MEDIUM",
        type: "Heavy Rain",
      },
      {
        id: "dwarahat",
        name: "Dwarahat",
        lat: 29.7775,
        lng: 79.4272,
        risk: "LOW",
        type: "Monitoring",
      },
    ],
  },

  {
    id: "chamoli",
    name: "Chamoli",
    lat: 30.402,
    lng: 79.328,
    risk: "CRITICAL",
    score: 91,
    alerts: 7,
    weather: "Extreme Rain",
    locations: [
      {
        id: "gopeshwar",
        name: "Gopeshwar",
        lat: 30.4037,
        lng: 79.3206,
        risk: "HIGH",
        type: "Landslide",
      },
      {
        id: "joshimath",
        name: "Joshimath",
        lat: 30.555,
        lng: 79.564,
        risk: "CRITICAL",
        type: "Slope Instability",
      },
    ],
  },

  {
    id: "pithoragarh",
    name: "Pithoragarh",
    lat: 29.5829,
    lng: 80.2182,
    risk: "HIGH",
    score: 82,
    alerts: 3,
    weather: "Rain",
    locations: [
      {
        id: "pithoragarh-city",
        name: "Pithoragarh City",
        lat: 29.5829,
        lng: 80.2182,
        risk: "HIGH",
        type: "Earthquake",
      },
      {
        id: "munsiyari",
        name: "Munsiyari",
        lat: 30.0668,
        lng: 80.239,
        risk: "HIGH",
        type: "Landslide",
      },
    ],
  },

  {
    id: "dehradun",
    name: "Dehradun",
    lat: 30.3165,
    lng: 78.0322,
    risk: "MEDIUM",
    score: 56,
    alerts: 2,
    weather: "Moderate Rain",
    locations: [
      {
        id: "dehradun-city",
        name: "Dehradun City",
        lat: 30.3165,
        lng: 78.0322,
        risk: "MEDIUM",
        type: "Flood",
      },
      {
        id: "mussoorie",
        name: "Mussoorie",
        lat: 30.4599,
        lng: 78.0664,
        risk: "HIGH",
        type: "Landslide",
      },
    ],
  },

  {
    id: "haridwar",
    name: "Haridwar",
    lat: 29.9457,
    lng: 78.1642,
    risk: "MEDIUM",
    score: 61,
    alerts: 2,
    weather: "Rain",
    locations: [
      {
        id: "haridwar-city",
        name: "Haridwar City",
        lat: 29.9457,
        lng: 78.1642,
        risk: "MEDIUM",
        type: "Flood",
      },
    ],
  },

  {
    id: "uttarkashi",
    name: "Uttarkashi",
    lat: 30.7268,
    lng: 78.4354,
    risk: "HIGH",
    score: 84,
    alerts: 5,
    weather: "Heavy Rain",
    locations: [
      {
        id: "uttarkashi-city",
        name: "Uttarkashi",
        lat: 30.7268,
        lng: 78.4354,
        risk: "HIGH",
        type: "Landslide",
      },
    ],
  },

  {
    id: "nainital",
    name: "Nainital",
    lat: 29.3919,
    lng: 79.4542,
    risk: "HIGH",
    score: 73,
    alerts: 3,
    weather: "Rain",
    locations: [
      {
        id: "nainital-city",
        name: "Nainital",
        lat: 29.3919,
        lng: 79.4542,
        risk: "HIGH",
        type: "Landslide",
      },
      {
        id: "bhimtal",
        name: "Bhimtal",
        lat: 29.3445,
        lng: 79.5639,
        risk: "MEDIUM",
        type: "Flood",
      },
    ],
  },
];

/* =========================================================
   HELPERS
========================================================= */

function normalizeRisk(value) {
  if (!value) return "MEDIUM";

  const risk = String(value).toUpperCase();

  if (risk.includes("CRITICAL")) return "CRITICAL";
  if (risk.includes("HIGH")) return "HIGH";
  if (risk.includes("MEDIUM")) return "MEDIUM";
  if (risk.includes("LOW")) return "LOW";

  return "MEDIUM";
}

function getRiskConfig(value) {
  return RISK_CONFIG[normalizeRisk(value)];
}

function formatRelativeTime(value) {
  if (!value) return "just now";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  const diff = Math.max(
    0,
    Math.floor((Date.now() - date.getTime()) / 1000)
  );

  if (diff < 60) return `${diff}s ago`;

  const minutes = Math.floor(diff / 60);

  if (minutes < 60) {
    return `${minutes}m ago`;
  }

  const hours = Math.floor(minutes / 60);

  return `${hours}h ago`;
}

function normalizeDistricts(payload) {
  const raw =
    payload?.districts ||
    payload?.data ||
    (Array.isArray(payload) ? payload : []);

  if (!Array.isArray(raw) || raw.length === 0) {
    return DISTRICTS;
  }

  return raw.map((item, index) => {
    const fallback =
      DISTRICTS.find(
        (district) =>
          district.id ===
          String(item.id || item.name)
            .toLowerCase()
            .replace(/\s+/g, "-")
      ) || DISTRICTS[index % DISTRICTS.length];

    return {
      ...fallback,
      ...item,
      id: item.id || fallback.id,
      name: item.name || fallback.name,
      lat: Number(item.lat ?? item.latitude ?? fallback.lat),
      lng: Number(
        item.lng ??
          item.lon ??
          item.longitude ??
          fallback.lng
      ),
      risk: normalizeRisk(
        item.risk ?? item.risk_level ?? fallback.risk
      ),
      score: Number(
        item.score ??
          item.risk_score ??
          fallback.score
      ),
      alerts: Number(
        item.alerts ??
          item.active_alerts ??
          fallback.alerts
      ),
      locations:
        Array.isArray(item.locations) &&
        item.locations.length
          ? item.locations.map((location) => ({
              ...location,
              lat: Number(
                location.lat ??
                  location.latitude ??
                  fallback.lat
              ),
              lng: Number(
                location.lng ??
                  location.longitude ??
                  fallback.lng
              ),
              risk: normalizeRisk(
                location.risk ??
                  location.risk_level
              ),
            }))
          : fallback.locations,
    };
  });
}

function normalizeAlerts(payload) {
  const raw =
    payload?.alerts ||
    payload?.data ||
    (Array.isArray(payload) ? payload : []);

  if (!Array.isArray(raw) || raw.length === 0) {
    return [
      {
        id: "fallback-1",
        severity: "CRITICAL",
        title: "Heavy rainfall in Chamoli",
        description:
          "Landslide risk remains elevated across slope-adjacent areas.",
        location: "Chamoli",
        timestamp: new Date().toISOString(),
      },
      {
        id: "fallback-2",
        severity: "WARNING",
        title: "Earthquake activity detected",
        description:
          "Monitoring remains active around Pithoragarh.",
        location: "Pithoragarh",
        timestamp: new Date(
          Date.now() - 1000 * 60 * 4
        ).toISOString(),
      },
      {
        id: "fallback-3",
        severity: "ADVISORY",
        title: "Flood monitoring active",
        description:
          "Water-level monitoring is active around Haridwar.",
        location: "Haridwar",
        timestamp: new Date(
          Date.now() - 1000 * 60 * 9
        ).toISOString(),
      },
    ];
  }

  return raw.map((item, index) => ({
    id: item.id || `alert-${index}`,
    severity:
      String(
        item.severity ||
          item.level ||
          item.risk ||
          "ADVISORY"
      ).toUpperCase(),
    title:
      item.title ||
      item.name ||
      "Disaster monitoring alert",
    description:
      item.description ||
      item.message ||
      "Monitoring event received from the intelligence layer.",
    location:
      item.location ||
      item.district ||
      "Uttarakhand",
    timestamp:
      item.timestamp ||
      item.created_at ||
      new Date().toISOString(),
  }));
}

/* =========================================================
   MAP CONTROLLER
========================================================= */

function MapViewportController({
  selectedPlace,
  zoomLevel,
  resetSignal,
}) {
  const map = useMap();

  useEffect(() => {
    if (!selectedPlace) return;

    map.flyTo(
      [
        selectedPlace.lat,
        selectedPlace.lng,
      ],
      zoomLevel,
      {
        duration: 1.1,
      }
    );
  }, [map, selectedPlace, zoomLevel]);

  useEffect(() => {
    if (!resetSignal) return;

    map.flyTo(
      UTTARAKHAND_CENTER,
      DEFAULT_ZOOM,
      {
        duration: 1,
      }
    );
  }, [map, resetSignal]);

  return null;
}

function MapClickCapture({ onMapClick }) {
  useMapEvents({
    click(event) {
      onMapClick?.(event.latlng);
    },
  });

  return null;
}

/* =========================================================
   SMALL UI COMPONENTS
========================================================= */

function StatusDot({ active = true }) {
  return (
    <span className="relative flex h-2.5 w-2.5">
      {active && (
        <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-50 animate-ping" />
      )}

      <span
        className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
          active
            ? "bg-emerald-400"
            : "bg-slate-600"
        }`}
      />
    </span>
  );
}

function SectionHeader({
  title,
  subtitle,
  icon: Icon,
  action,
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div className="flex items-center gap-3">
        {Icon && (
          <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
            <Icon className="w-4 h-4 text-indigo-400" />
          </div>
        )}

        <div>
          <h2 className="text-xs font-bold uppercase tracking-[0.16em] text-slate-200">
            {title}
          </h2>

          {subtitle && (
            <p className="text-[11px] text-slate-500 mt-0.5">
              {subtitle}
            </p>
          )}
        </div>
      </div>

      {action}
    </div>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  tone = "indigo",
  onClick,
}) {
  const tones = {
    red: {
      border: "border-red-500/20",
      icon: "bg-red-500/10 text-red-400",
      value: "text-red-400",
    },
    orange: {
      border: "border-orange-500/20",
      icon: "bg-orange-500/10 text-orange-400",
      value: "text-orange-400",
    },
    emerald: {
      border: "border-emerald-500/20",
      icon: "bg-emerald-500/10 text-emerald-400",
      value: "text-emerald-400",
    },
    indigo: {
      border: "border-indigo-500/20",
      icon: "bg-indigo-500/10 text-indigo-400",
      value: "text-indigo-400",
    },
    yellow: {
      border: "border-yellow-500/20",
      icon: "bg-yellow-500/10 text-yellow-400",
      value: "text-yellow-400",
    },
  };

  const style = tones[tone] || tones.indigo;

  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-left w-full rounded-2xl border ${style.border} bg-[#111827]/80 p-4 transition-all duration-200 hover:-translate-y-0.5 hover:bg-[#151e2f] hover:border-slate-700 group`}
    >
      <div className="flex items-start justify-between">
        <div
          className={`w-9 h-9 rounded-xl ${style.icon} flex items-center justify-center`}
        >
          <Icon className="w-4 h-4" />
        </div>

        <ChevronRight className="w-4 h-4 text-slate-700 group-hover:text-slate-400 transition" />
      </div>

      <div
        className={`text-2xl font-black mt-4 ${style.value}`}
      >
        {value}
      </div>

      <div className="text-[11px] font-semibold text-slate-300 mt-1">
        {label}
      </div>

      {detail && (
        <div className="text-[10px] text-slate-600 mt-1">
          {detail}
        </div>
      )}
    </button>
  );
}

function RiskBadge({ risk }) {
  const config = getRiskConfig(risk);

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md border ${config.border} bg-slate-950/40 ${config.text} text-[9px] font-bold uppercase tracking-wider`}
    >
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{
          backgroundColor: config.color,
        }}
      />

      {config.label}
    </span>
  );
}

/* =========================================================
   SEARCH PANEL
========================================================= */

function SearchPanel({
  query,
  setQuery,
  districts,
  onSelect,
  onClose,
}) {
  const results = useMemo(() => {
    const normalized = query.trim().toLowerCase();

    if (!normalized) return [];

    const output = [];

    districts.forEach((district) => {
      if (
        district.name
          .toLowerCase()
          .includes(normalized)
      ) {
        output.push({
          type: "District",
          id: district.id,
          name: district.name,
          lat: district.lat,
          lng: district.lng,
          risk: district.risk,
          district: district.name,
        });
      }

      (district.locations || []).forEach(
        (location) => {
          if (
            location.name
              .toLowerCase()
              .includes(normalized)
          ) {
            output.push({
              type: "Location",
              ...location,
              district: district.name,
            });
          }
        }
      );
    });

    return output.slice(0, 8);
  }, [districts, query]);

  return (
    <div className="absolute top-14 left-0 right-0 z-[1000] rounded-2xl border border-slate-700/80 bg-[#0d1420]/98 backdrop-blur-xl shadow-2xl overflow-hidden">
      <div className="px-3 py-2 border-b border-slate-800 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest text-slate-500">
          Search intelligence
        </span>

        <button
          type="button"
          onClick={onClose}
          className="text-slate-600 hover:text-slate-300"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {results.length === 0 ? (
        <div className="px-4 py-6 text-center">
          <Search className="w-5 h-5 text-slate-700 mx-auto mb-2" />

          <p className="text-xs text-slate-500">
            No monitored location found.
          </p>
        </div>
      ) : (
        <div className="max-h-80 overflow-y-auto">
          {results.map((result) => (
            <button
              key={`${result.type}-${result.id}`}
              type="button"
              onClick={() => {
                onSelect(result);
                onClose();
              }}
              className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-slate-800/50 transition border-b border-slate-800/60 last:border-0"
            >
              <div className="w-8 h-8 rounded-lg bg-slate-800 flex items-center justify-center">
                <MapPin className="w-3.5 h-3.5 text-indigo-400" />
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-slate-200 truncate">
                    {result.name}
                  </span>

                  <span className="text-[8px] uppercase text-slate-600">
                    {result.type}
                  </span>
                </div>

                <div className="text-[10px] text-slate-500 mt-0.5">
                  {result.district}
                </div>
              </div>

              <RiskBadge risk={result.risk} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* =========================================================
   MAP
========================================================= */

function RiskMap({
  districts,
  selectedDisaster,
  selectedRisk,
  onSelectDistrict,
  onSelectLocation,
  selectedPlace,
  mapResetSignal,
}) {
    const mapRef = useRef(null);
  const [mapZoom, setMapZoom] = useState(DEFAULT_ZOOM);

  const filteredDistricts = useMemo(() => {
    if (selectedRisk === "ALL") {
      return districts;
    }

    return districts.filter(
      (district) =>
        normalizeRisk(district.risk) ===
        normalizeRisk(selectedRisk)
    );
  }, [districts, selectedRisk]);

  return (
    <div className="relative h-[520px] overflow-hidden rounded-2xl border border-slate-800 bg-[#080c13]">
      <MapContainer
        center={UTTARAKHAND_CENTER}
        zoom={DEFAULT_ZOOM}
        minZoom={6}
        maxZoom={18}
        scrollWheelZoom={true}
        zoomControl={false}
        className="h-full w-full"
        whenReady={(event) => {
          const map = event.target;

          mapRef.current = map;
          map.on("zoomend", () => {
            setMapZoom(map.getZoom());
          });
        }}
      >
        <TileLayer
          attribution='&copy; OpenStreetMap contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <MapViewportController
          selectedPlace={selectedPlace}
          zoomLevel={
            selectedPlace?.type === "Location"
              ? 15
              : 10
          }
          resetSignal={mapResetSignal}
        />

        <MapClickCapture />

        {filteredDistricts.map((district) => {
          const config = getRiskConfig(
            district.risk
          );

          return (
            <React.Fragment key={district.id}>
              {/* Full colored district risk zone */}
              <Circle
                center={[
                  district.lat,
                  district.lng,
                ]}
                radius={
                  district.risk === "CRITICAL"
                    ? 18000
                    : district.risk === "HIGH"
                    ? 15000
                    : district.risk === "MEDIUM"
                    ? 12000
                    : 9000
                }
                pathOptions={{
                  color: config.color,
                  fillColor: config.fill,
                  fillOpacity:
                    district.risk === "CRITICAL"
                      ? 0.34
                      : 0.27,
                  weight: 2,
                }}
                eventHandlers={{
                  click: () =>
                    onSelectDistrict(district),
                }}
              />

              <CircleMarker
                center={[
                  district.lat,
                  district.lng,
                ]}
                radius={
                  district.risk === "CRITICAL"
                    ? 10
                    : 8
                }
                pathOptions={{
                  color: "#ffffff",
                  weight: 1.5,
                  fillColor: config.color,
                  fillOpacity: 1,
                }}
                eventHandlers={{
                  click: () =>
                    onSelectDistrict(district),
                }}
              >
                <Popup>
                  <div className="min-w-[190px] text-slate-900">
                    <div className="font-bold text-sm">
                      {district.name}
                    </div>

                    <div className="text-xs mt-1">
                      Risk:{" "}
                      <strong>
                        {config.label}
                      </strong>
                    </div>

                    <div className="text-xs mt-1">
                      Risk score:{" "}
                      <strong>
                        {district.score}
                      </strong>
                    </div>

                    <div className="text-xs mt-1">
                      Active alerts:{" "}
                      <strong>
                        {district.alerts}
                      </strong>
                    </div>
                  </div>
                </Popup>
              </CircleMarker>

              {/* Local locations become visible at deeper zoom */}
              {mapZoom >= 9 &&
                (district.locations || []).map(
                  (location) => {
                    const locationRisk =
                      getRiskConfig(
                        location.risk
                      );

                    return (
                      <CircleMarker
                        key={location.id}
                        center={[
                          location.lat,
                          location.lng,
                        ]}
                        radius={6}
                        pathOptions={{
                          color: "#ffffff",
                          weight: 1,
                          fillColor:
                            locationRisk.color,
                          fillOpacity: 1,
                        }}
                        eventHandlers={{
                          click: () =>
                            onSelectLocation(
                              location,
                              district
                            ),
                        }}
                      >
                        <Popup>
                          <div className="min-w-[180px] text-slate-900">
                            <div className="font-bold text-sm">
                              {location.name}
                            </div>

                            <div className="text-xs mt-1">
                              {location.type}
                            </div>

                            <div className="text-xs mt-1">
                              Risk:{" "}
                              <strong>
                                {
                                  locationRisk.label
                                }
                              </strong>
                            </div>

                            <div className="text-[10px] mt-2 text-slate-500">
                              Click marker to
                              zoom deeper.
                            </div>
                          </div>
                        </Popup>
                      </CircleMarker>
                    );
                  }
                )}
            </React.Fragment>
          );
        })}
      </MapContainer>

      {/* Map toolbar */}
      <div className="absolute z-[900] top-3 left-3 flex flex-col gap-1.5">
      <button
  type="button"
  title="Zoom in"
  onClick={() => mapRef.current?.zoomIn()}
  className="w-9 h-9 rounded-lg border border-slate-700 bg-[#101827]/95 backdrop-blur text-slate-300 hover:text-white hover:bg-[#182235] flex items-center justify-center"
>
  <Plus className="w-4 h-4" />
</button>

<button
  type="button"
  title="Zoom out"
  onClick={() => mapRef.current?.zoomOut()}
  className="w-9 h-9 rounded-lg border border-slate-700 bg-[#101827]/95 backdrop-blur text-slate-300 hover:text-white hover:bg-[#182235] flex items-center justify-center"
>
  <Minus className="w-4 h-4" />
</button>

        <button
          type="button"
          title="Zoom out"
          onClick={() => {
            document
              .querySelector(
                ".leaflet-container"
              )
              ?.dispatchEvent(
                new WheelEvent("wheel", {
                  deltaY: 400,
                })
              );
          }}
          className="w-9 h-9 rounded-lg border border-slate-700 bg-[#101827]/95 backdrop-blur text-slate-300 hover:text-white hover:bg-[#182235] flex items-center justify-center"
        >
          <Minus className="w-4 h-4" />
        </button>
      </div>

      {/* Legend */}
      <div className="absolute z-[900] bottom-3 left-3 rounded-xl border border-slate-700/80 bg-[#0b111c]/95 backdrop-blur px-3 py-2.5 shadow-xl">
        <div className="text-[9px] uppercase tracking-widest text-slate-500 mb-2">
          Risk zones
        </div>

        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
          {Object.entries(RISK_CONFIG).map(
            ([key, config]) => (
              <div
                key={key}
                className="flex items-center gap-2"
              >
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{
                    backgroundColor:
                      config.color,
                  }}
                />

                <span className="text-[9px] text-slate-400">
                  {config.label}
                </span>
              </div>
            )
          )}
        </div>
      </div>

      {/* Current zoom */}
      <div className="absolute z-[900] top-3 right-3 rounded-lg border border-slate-700 bg-[#0b111c]/90 backdrop-blur px-2.5 py-1.5 text-[9px] text-slate-500">
        ZOOM {mapZoom}
      </div>
    </div>
  );
}

/* =========================================================
   ALERT PANEL
========================================================= */

function AlertPanel({
  alerts,
  onAlertClick,
}) {
  return (
    <div className="space-y-2">
      {alerts.map((alert) => {
        const severity =
          alert.severity === "CRITICAL"
            ? "CRITICAL"
            : alert.severity === "WARNING"
            ? "WARNING"
            : "ADVISORY";

        const config =
          severity === "CRITICAL"
            ? RISK_CONFIG.CRITICAL
            : severity === "WARNING"
            ? RISK_CONFIG.MEDIUM
            : RISK_CONFIG.LOW;

        return (
          <button
            key={alert.id}
            type="button"
            onClick={() => onAlertClick?.(alert)}
            className={`w-full text-left rounded-xl border ${config.border} bg-slate-950/30 hover:bg-slate-900/60 transition p-3`}
          >
            <div className="flex items-start gap-3">
              <div
                className="mt-0.5 w-2 h-2 rounded-full shrink-0"
                style={{
                  backgroundColor:
                    config.color,
                }}
              />

              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={`text-[9px] font-bold uppercase tracking-wider ${config.text}`}
                  >
                    {severity}
                  </span>

                  <span className="text-[9px] text-slate-600">
                    {formatRelativeTime(
                      alert.timestamp
                    )}
                  </span>
                </div>

                <div className="text-xs font-semibold text-slate-200 mt-1">
                  {alert.title}
                </div>

                <p className="text-[10px] text-slate-500 mt-1 leading-relaxed">
                  {alert.description}
                </p>

                <div className="flex items-center gap-1 mt-2 text-[9px] text-slate-600">
                  <MapPin className="w-3 h-3" />
                  {alert.location}
                </div>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

/* =========================================================
   AI PANEL
========================================================= */

function AIWorkspace({
  aiQuery,
  setAiQuery,
  aiResponse,
  isGenerating,
  onAsk,
}) {
  const suggestions = [
    "What is the current landslide risk in Almora?",
    "Which regions need immediate monitoring?",
    "Explain the current weather risk.",
    "What are the major active threats?",
  ];

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 rounded-2xl border border-slate-800 bg-[#0a0f18] overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
              <Zap className="w-4 h-4 text-indigo-400" />
            </div>

            <div>
              <div className="text-xs font-bold text-slate-200">
                Disaster Intelligence AI
              </div>

              <div className="flex items-center gap-1.5 text-[9px] text-emerald-400 mt-0.5">
                <StatusDot />
                Groq intelligence layer
              </div>
            </div>
          </div>
        </div>

        <div className="p-5">
          <div className="rounded-2xl border border-indigo-500/10 bg-indigo-500/[0.03] p-4 min-h-[180px]">
            {isGenerating ? (
              <div className="flex items-center gap-3 text-indigo-400">
                <RefreshCw className="w-4 h-4 animate-spin" />

                <div>
                  <div className="text-xs font-semibold">
                    Analyzing intelligence data...
                  </div>

                  <div className="text-[10px] text-slate-600 mt-1">
                    Querying FastAPI intelligence
                    layer.
                  </div>
                </div>
              </div>
            ) : (
              <>
                <div className="text-[9px] uppercase tracking-widest text-indigo-400/70 mb-2">
                  AI Analysis
                </div>

                <p className="text-xs leading-6 text-slate-300 whitespace-pre-wrap">
                  {aiResponse ||
                    "Ask the Disaster Intelligence engine about risk, alerts, weather, locations or monitored regions."}
                </p>
              </>
            )}
          </div>

          <div className="mt-5">
            <div className="text-[9px] uppercase tracking-widest text-slate-600 mb-2">
              Suggested queries
            </div>

            <div className="flex flex-wrap gap-2">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => {
                    setAiQuery(suggestion);
                  }}
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
              onChange={(event) =>
                setAiQuery(event.target.value)
              }
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey
                ) {
                  event.preventDefault();
                  onAsk();
                }
              }}
              rows={3}
              placeholder="Ask Disaster Intelligence..."
              className="w-full resize-none rounded-2xl border border-slate-800 bg-[#080c13] px-4 py-3 pr-12 text-xs text-slate-200 placeholder:text-slate-700 outline-none focus:border-indigo-500/50"
            />

            <button
              type="button"
              disabled={
                isGenerating ||
                !aiQuery.trim()
              }
              onClick={onAsk}
              className="absolute right-3 bottom-3 w-8 h-8 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center"
            >
              <Send className="w-3.5 h-3.5 text-white" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* =========================================================
   MAIN COMPONENT
========================================================= */

export default function DisasterDashboard() {
  const { user, logout } = useAuth();

  const [activeTab, setActiveTab] =
    useState("Dashboard");

  const [districts, setDistricts] =
    useState(DISTRICTS);

  const [alerts, setAlerts] = useState([]);

  const [overview, setOverview] = useState(null);

  const [apiLoading, setApiLoading] =
    useState(true);

  const [apiError, setApiError] =
    useState("");

  const [lastSync, setLastSync] =
    useState(new Date());

  const [selectedDisaster, setSelectedDisaster] =
    useState("ALL");

  const [selectedRisk, setSelectedRisk] =
    useState("ALL");

  const [selectedPlace, setSelectedPlace] =
    useState(null);

  const [mapResetSignal, setMapResetSignal] =
    useState(0);

  const [searchQuery, setSearchQuery] =
    useState("");

  const [searchOpen, setSearchOpen] =
    useState(false);

  const [notificationsOpen, setNotificationsOpen] =
    useState(false);

  const [profileOpen, setProfileOpen] =
    useState(false);

  const [mobileMenuOpen, setMobileMenuOpen] =
    useState(false);

  const [aiQuery, setAiQuery] = useState("");

  const [aiResponse, setAiResponse] =
    useState(
      "Disaster Intelligence is ready. Ask about active threats, locations, weather risk, landslides, floods or regional risk."
    );

  const [isGenerating, setIsGenerating] =
    useState(false);

  const [selectedAlert, setSelectedAlert] =
    useState(null);

  const [refreshing, setRefreshing] =
    useState(false);

  const [weather, setWeather] = useState(null);
  const [weatherLoading, setWeatherLoading] = useState(true);
  const [weatherError, setWeatherError] = useState("");

  const searchRef = useRef(null);

  /* =====================================================
     LOAD DASHBOARD
  ===================================================== */

  const loadDashboard = useCallback(
    async (manual = false) => {
      try {
        if (manual) {
          setRefreshing(true);
        } else {
          setApiLoading(true);
        }

        const [
          overviewResult,
          alertsResult,
          districtsResult,
        ] = await Promise.allSettled([
          dashboardApi.getOverview(),
          dashboardApi.getAlerts(),
          dashboardApi.getDistricts(),
        ]);

        if (
          overviewResult.status ===
          "fulfilled"
        ) {
          setOverview(
            overviewResult.value
          );
        }

        if (
          alertsResult.status ===
          "fulfilled"
        ) {
          setAlerts(
            normalizeAlerts(
              alertsResult.value
            )
          );
        } else {
          setAlerts(normalizeAlerts(null));
        }

        if (
          districtsResult.status ===
          "fulfilled"
        ) {
          setDistricts(
            normalizeDistricts(
              districtsResult.value
            )
          );
        } else {
          setDistricts(DISTRICTS);
        }

        const everythingFailed =
          overviewResult.status ===
            "rejected" &&
          alertsResult.status ===
            "rejected" &&
          districtsResult.status ===
            "rejected";

        setApiError(
          everythingFailed
            ? "Backend intelligence service is unreachable. Showing resilient local monitoring data."
            : ""
        );

        setLastSync(new Date());
      } catch (error) {
        setApiError(
          error?.message ||
            "Unable to synchronize dashboard."
        );
      } finally {
        setApiLoading(false);
        setRefreshing(false);
      }
    },
    []
  );

  useEffect(() => {
    loadDashboard();

    const interval = setInterval(() => {
      loadDashboard();
    }, 30000);

    return () => {
      clearInterval(interval);
    };
  }, [loadDashboard]);

  /* =====================================================
     LIVE WEATHER
  ===================================================== */

  const fetchWeather = useCallback(async () => {
    const place = selectedPlace || DISTRICTS[0];
    const latitude = Number(place?.lat ?? DISTRICTS[0].lat);
    const longitude = Number(place?.lng ?? DISTRICTS[0].lng);

    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      setWeatherError("Invalid location coordinates");
      setWeatherLoading(false);
      return;
    }

    try {
      setWeatherLoading(true);
      setWeatherError("");

      const response = await fetch(
        `${API_BASE_URL}/api/weather?latitude=${latitude}&longitude=${longitude}`
      );

      if (!response.ok) {
        throw new Error(`Weather request failed (${response.status})`);
      }

      const data = await response.json();

      setWeather(data);
    } catch (error) {
      console.error("Weather fetch error:", error);
      setWeatherError("Live weather unavailable");
    } finally {
      setWeatherLoading(false);
    }
  }, [selectedPlace]);

  useEffect(() => {
    fetchWeather();

    const interval = setInterval(() => {
      fetchWeather();
    }, 10 * 60 * 1000);

    return () => clearInterval(interval);
  }, [fetchWeather]);

  /* =====================================================
     SEARCH OUTSIDE CLICK
  ===================================================== */

  useEffect(() => {
    const handleClick = (event) => {
      if (
        searchRef.current &&
        !searchRef.current.contains(
          event.target
        )
      ) {
        setSearchOpen(false);
      }
    };

    document.addEventListener(
      "mousedown",
      handleClick
    );

    return () => {
      document.removeEventListener(
        "mousedown",
        handleClick
      );
    };
  }, []);

  /* =====================================================
     METRICS
  ===================================================== */

  const computedMetrics = useMemo(() => {
    const activeAlerts =
      Number(
        overview?.active_alerts ??
          overview?.alerts ??
          overview?.total_alerts
      ) ||
      alerts.length;

    const highRiskZones =
      Number(
        overview?.high_risk_zones ??
          overview?.risk_zones
      ) ||
      districts.filter(
        (district) =>
          ["HIGH", "CRITICAL"].includes(
            normalizeRisk(district.risk)
          )
      ).length;

    const monitoredLocations =
      Number(
        overview?.monitored_locations ??
          overview?.locations
      ) ||
      districts.reduce(
        (total, district) =>
          total +
          1 +
          (district.locations?.length || 0),
        0
      );

    const overallRisk =
      Number(
        overview?.overall_risk ??
          overview?.risk_score
      ) ||
      Math.round(
        districts.reduce(
          (total, district) =>
            total + Number(district.score || 0),
          0
        ) /
          Math.max(districts.length, 1)
      );

    return {
      activeAlerts,
      highRiskZones,
      monitoredLocations,
      overallRisk,
    };
  }, [districts, alerts, overview]);

  /* =====================================================
     MAP ACTIONS
  ===================================================== */

  const handleDistrictSelect = (district) => {
    setSelectedPlace({
      type: "District",
      ...district,
    });

    setActiveTab("Live Monitoring");
  };

  const handleLocationSelect = (
    location,
    district
  ) => {
    setSelectedPlace({
      type: "Location",
      ...location,
      district: district.name,
    });

    setActiveTab("Live Monitoring");
  };

  const handleSearchSelect = (result) => {
    setSelectedPlace(result);
    setActiveTab("Live Monitoring");
  };

  /* =====================================================
     AI
  ===================================================== */

  const handleAiAsk = async () => {
    const query = aiQuery.trim();

    if (!query || isGenerating) {
      return;
    }

    try {
      setIsGenerating(true);

      const response = await aiApi.ask(
        query,
        selectedPlace?.name || null
      );

      setAiResponse(
        response?.answer ||
          response?.response ||
          response?.message ||
          "The AI service returned no answer."
      );
    } catch (error) {
      setAiResponse(
        error?.message ===
          "SESSION_EXPIRED"
          ? "Your session has expired. Please sign in again."
          : "Unable to reach the Disaster Intelligence AI service. Check the FastAPI backend and Groq configuration."
      );
    } finally {
      setIsGenerating(false);
    }
  };

  /* =====================================================
     NAVIGATION
  ===================================================== */

  const navigateTab = (tab) => {
    setActiveTab(tab);
    setMobileMenuOpen(false);
  };

  /* =====================================================
     RENDER DASHBOARD
  ===================================================== */

  const renderDashboard = () => {
    return (
      <>
        {/* KPI ROW */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
          <MetricCard
            icon={ShieldAlert}
            label="Active Threats"
            value={
              apiLoading
                ? "—"
                : computedMetrics.activeAlerts
            }
            detail="Prioritized intelligence events"
            tone="red"
            onClick={() =>
              setActiveTab("Live Monitoring")
            }
          />

          <MetricCard
            icon={AlertTriangle}
            label="High Risk Zones"
            value={
              apiLoading
                ? "—"
                : computedMetrics.highRiskZones
            }
            detail="High + critical monitoring areas"
            tone="orange"
            onClick={() =>
              setActiveTab("Risk Analytics")
            }
          />

          <MetricCard
            icon={MapPin}
            label="Monitored Locations"
            value={
              apiLoading
                ? "—"
                : computedMetrics.monitoredLocations
            }
            detail="Districts and local locations"
            tone="indigo"
            onClick={() =>
              setActiveTab("Live Monitoring")
            }
          />

          <MetricCard
            icon={Activity}
            label="Overall Risk"
            value={
              apiLoading
                ? "—"
                : computedMetrics.overallRisk
            }
            detail="Composite regional risk score"
            tone="yellow"
            onClick={() =>
              setActiveTab("Risk Analytics")
            }
          />
        </div>

        {/* MAIN */}
        <div className="grid grid-cols-1 xl:grid-cols-[1.55fr_0.85fr] gap-4">
          {/* MAP */}
          <section className="rounded-2xl border border-slate-800/90 bg-[#0d1420]/80 backdrop-blur-xl p-4 shadow-xl">
            <SectionHeader
              title="Live Risk Map"
              subtitle="Uttarakhand geospatial disaster intelligence"
              icon={Navigation}
              action={
                <button
                  type="button"
                  onClick={() =>
                    setActiveTab(
                      "Live Monitoring"
                    )
                  }
                  className="text-[10px] font-semibold text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
                >
                  Open monitoring
                  <ChevronRight className="w-3 h-3" />
                </button>
              }
            />

            <div className="flex flex-wrap gap-2 mb-3">
              {[
                "ALL",
                "FLOOD",
                "EARTHQUAKE",
                "FIRE",
                "LANDSLIDE",
              ].map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() =>
                    setSelectedDisaster(type)
                  }
                  className={`px-3 py-1.5 rounded-lg border text-[9px] font-bold tracking-wider transition ${
                    selectedDisaster === type
                      ? "border-indigo-500/50 bg-indigo-500/10 text-indigo-300"
                      : "border-slate-800 bg-slate-950/40 text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {type === "ALL"
                    ? "ALL HAZARDS"
                    : type}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap gap-2 mb-4">
              {[
                "ALL",
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL",
              ].map((risk) => {
                const config =
                  risk === "ALL"
                    ? null
                    : getRiskConfig(risk);

                return (
                  <button
                    key={risk}
                    type="button"
                    onClick={() =>
                      setSelectedRisk(risk)
                    }
                    className={`px-2.5 py-1 rounded-md border text-[8px] font-bold uppercase tracking-wider ${
                      selectedRisk === risk
                        ? config
                          ? `${config.border} ${config.text} bg-slate-900`
                          : "border-indigo-500/50 text-indigo-300 bg-indigo-500/10"
                        : "border-slate-800 text-slate-600 bg-slate-950/30"
                    }`}
                  >
                    {risk === "ALL"
                      ? "ALL RISK"
                      : risk}
                  </button>
                );
              })}
            </div>

            <RiskMap
              districts={districts}
              selectedDisaster={
                selectedDisaster
              }
              selectedRisk={selectedRisk}
              onSelectDistrict={
                handleDistrictSelect
              }
              onSelectLocation={
                handleLocationSelect
              }
              selectedPlace={selectedPlace}
              mapResetSignal={
                mapResetSignal
              }
            />

            {selectedPlace && (
              <div className="mt-3 rounded-xl border border-indigo-500/20 bg-indigo-500/[0.04] px-3 py-2.5 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <MapPin className="w-3.5 h-3.5 text-indigo-400" />

                  <div>
                    <div className="text-[10px] font-semibold text-slate-300">
                      Focused location
                    </div>

                    <div className="text-xs text-indigo-300">
                      {selectedPlace.name}
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    setSelectedPlace(null);
                    setMapResetSignal(
                      (value) => value + 1
                    );
                  }}
                  className="text-[9px] text-slate-600 hover:text-slate-300"
                >
                  Reset map
                </button>
              </div>
            )}
          </section>

          {/* RIGHT */}
          <div className="space-y-4">
            {/* SYSTEM STATUS */}
            <section className="rounded-2xl border border-slate-800/90 bg-[#0d1420]/80 p-4 shadow-xl">
              <SectionHeader
                title="System Operational"
                subtitle="Platform health and telemetry"
                icon={Radio}
              />

              <div className="grid grid-cols-2 gap-2">
                {[
                  [
                    "API",
                    !apiError,
                  ],
                  [
                    "Monitoring",
                    true,
                  ],
                  [
                    "AI Engine",
                    true,
                  ],
                  [
                    "Map Service",
                    true,
                  ],
                ].map(([name, active]) => (
                  <div
                    key={name}
                    className="rounded-xl border border-slate-800 bg-slate-950/30 p-3"
                  >
                    <div className="flex items-center gap-2">
                      <StatusDot active={active} />

                      <span className="text-[10px] font-semibold text-slate-300">
                        {name}
                      </span>
                    </div>

                    <div
                      className={`text-[9px] mt-2 ${
                        active
                          ? "text-emerald-400"
                          : "text-red-400"
                      }`}
                    >
                      {active
                        ? "Operational"
                        : "Degraded"}
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-3 flex items-center justify-between text-[9px] text-slate-600">
                <span>
                  Last sync{" "}
                  {lastSync.toLocaleTimeString()}
                </span>

                <button
                  type="button"
                  onClick={() =>
                    loadDashboard(true)
                  }
                  className="text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
                >
                  <RefreshCw
                    className={`w-3 h-3 ${
                      refreshing
                        ? "animate-spin"
                        : ""
                    }`}
                  />
                  Sync
                </button>
              </div>
            </section>

            {/* WEATHER */}
            <section className="rounded-2xl border border-slate-800/90 bg-[#0d1420]/80 p-4 shadow-xl">
              <SectionHeader
                title="Weather Risk"
                subtitle="Regional atmospheric indicators"
                icon={CloudRain}
                action={
                  <span className="text-[9px] text-yellow-400">
                    Monitoring
                  </span>
                }
              />

              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-slate-800 bg-slate-950/30 p-3">
                  <div className="flex items-center gap-2 text-slate-500">
                    <Thermometer className="w-3.5 h-3.5" />
                    <span className="text-[9px]">Temperature</span>
                  </div>
                  <div className="text-xl font-bold text-slate-200 mt-2">
                    {weatherLoading ? "--" : weather?.current?.temperature != null ? `${weather.current.temperature}°C` : "--"}
                  </div>
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-950/30 p-3">
                  <div className="flex items-center gap-2 text-slate-500">
                    <CloudRain className="w-3.5 h-3.5" />
                    <span className="text-[9px]">Rainfall</span>
                  </div>
                  <div className="text-xl font-bold text-slate-200 mt-2">
                    {weatherLoading ? "--" : weather?.current?.rain != null ? `${weather.current.rain} mm` : "--"}
                  </div>
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-950/30 p-3">
                  <div className="flex items-center gap-2 text-slate-500">
                    <Droplets className="w-3.5 h-3.5" />
                    <span className="text-[9px]">Humidity</span>
                  </div>
                  <div className="text-xl font-bold text-slate-200 mt-2">
                    {weatherLoading ? "--" : weather?.current?.humidity != null ? `${weather.current.humidity}%` : "--"}
                  </div>
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-950/30 p-3">
                  <div className="flex items-center gap-2 text-slate-500">
                    <Wind className="w-3.5 h-3.5" />
                    <span className="text-[9px]">Wind</span>
                  </div>
                  <div className="text-xl font-bold text-slate-200 mt-2">
                    {weatherLoading ? "--" : weather?.current?.wind_speed != null ? `${weather.current.wind_speed} km/h` : "--"}
                  </div>
                </div>
              </div>

              <div className="mt-3 flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/20 px-3 py-2">
                <span className="text-[9px] text-slate-600">
                  {selectedPlace?.name || "Almora"} • {weather?.current?.condition || (weatherLoading ? "Loading..." : "Unknown")}
                </span>
                <span className={`text-[8px] uppercase ${weatherError ? "text-red-400" : "text-emerald-400"}`}>
                  {weatherError ? "OFFLINE" : "LIVE"}
                </span>
              </div>

              {weatherError && (
                <div className="mt-2 text-[9px] text-red-400">
                  {weatherError}
                </div>
              )}

              <button
                type="button"
                onClick={() =>
                  setActiveTab(
                    "Risk Analytics"
                  )
                }
                className="w-full mt-3 rounded-xl border border-yellow-500/20 bg-yellow-500/[0.04] p-3 text-left hover:bg-yellow-500/[0.08] transition"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-yellow-400">
                    WEATHER RISK
                  </span>

                  <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
                </div>

                <div className="text-xs text-slate-300 mt-1">
                  Elevated precipitation may increase
                  slope instability.
                </div>
              </button>
            </section>

            {/* QUICK AI */}
            <section className="rounded-2xl border border-indigo-500/10 bg-indigo-500/[0.025] p-4 shadow-xl">
              <SectionHeader
                title="AI Intelligence"
                subtitle="Ask the disaster intelligence engine"
                icon={Zap}
                action={
                  <button
                    type="button"
                    onClick={() =>
                      setActiveTab(
                        "AI Intelligence"
                      )
                    }
                    className="text-[9px] text-indigo-400"
                  >
                    Full AI
                  </button>
                }
              />

              <div className="relative">
                <input
                  value={aiQuery}
                  onChange={(event) =>
                    setAiQuery(
                      event.target.value
                    )
                  }
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter"
                    ) {
                      handleAiAsk();
                    }
                  }}
                  placeholder="Ask about Almora, floods, landslides..."
                  className="w-full h-10 rounded-xl border border-slate-800 bg-slate-950/50 px-3 pr-10 text-[10px] text-slate-300 placeholder:text-slate-700 outline-none focus:border-indigo-500/40"
                />

                <button
                  type="button"
                  onClick={handleAiAsk}
                  disabled={!aiQuery.trim()}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-indigo-400 disabled:text-slate-700"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>
            </section>
          </div>
        </div>

        {/* ALERT CENTER */}
        <section className="rounded-2xl border border-slate-800/90 bg-[#0d1420]/80 p-4 shadow-xl">
          <SectionHeader
            title="Alert Center"
            subtitle="Prioritized live intelligence events"
            icon={Bell}
            action={
              <span className="flex items-center gap-1.5 text-[9px] text-emerald-400">
                <StatusDot />
                LIVE
              </span>
            }
          />

          <AlertPanel
            alerts={alerts}
            onAlertClick={(alert) => {
              setSelectedAlert(alert);
              setActiveTab(
                "Live Monitoring"
              );
            }}
          />
        </section>
      </>
    );
  };

  /* =====================================================
     LIVE MONITORING
  ===================================================== */

  const renderLiveMonitoring = () => {
    return (
      <>
        <section className="rounded-2xl border border-slate-800/90 bg-[#0d1420]/80 p-4 shadow-xl">
          <SectionHeader
            title="Live Monitoring"
            subtitle="Real-time geospatial threat monitoring"
            icon={Radio}
            action={
              <div className="flex items-center gap-2">
                <StatusDot />
                <span className="text-[9px] text-emerald-400">
                  MONITORING ACTIVE
                </span>
              </div>
            }
          />

          <RiskMap
            districts={districts}
            selectedDisaster={
              selectedDisaster
            }
            selectedRisk={selectedRisk}
            onSelectDistrict={
              handleDistrictSelect
            }
            onSelectLocation={
              handleLocationSelect
            }
            selectedPlace={selectedPlace}
            mapResetSignal={
              mapResetSignal
            }
          />
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <section className="rounded-2xl border border-slate-800 bg-[#0d1420]/80 p-4">
            <SectionHeader
              title="Monitored Regions"
              subtitle="Click a region to zoom into it"
              icon={MapPin}
            />

            <div className="space-y-2">
              {districts.map((district) => {
                const config =
                  getRiskConfig(
                    district.risk
                  );

                return (
                  <button
                    key={district.id}
                    type="button"
                    onClick={() =>
                      handleDistrictSelect(
                        district
                      )
                    }
                    className="w-full flex items-center gap-3 p-3 rounded-xl border border-slate-800 bg-slate-950/20 hover:bg-slate-900/60 transition text-left"
                  >
                    <div
                      className="w-2 h-10 rounded-full"
                      style={{
                        backgroundColor:
                          config.color,
                      }}
                    />

                    <div className="flex-1">
                      <div className="text-xs font-semibold text-slate-200">
                        {district.name}
                      </div>

                      <div className="text-[9px] text-slate-600 mt-1">
                        {district.locations?.length ||
                          0}{" "}
                        local locations •{" "}
                        {district.alerts} active
                        alerts
                      </div>
                    </div>

                    <RiskBadge
                      risk={district.risk}
                    />

                    <ChevronRight className="w-3.5 h-3.5 text-slate-700" />
                  </button>
                );
              })}
            </div>
          </section>

          <section className="rounded-2xl border border-slate-800 bg-[#0d1420]/80 p-4">
            <SectionHeader
              title="Live Event Stream"
              subtitle="Latest intelligence events"
              icon={Activity}
            />

            <AlertPanel
              alerts={alerts}
              onAlertClick={(alert) => {
                setSelectedAlert(alert);
              }}
            />
          </section>
        </div>
      </>
    );
  };

  /* =====================================================
     ANALYTICS
  ===================================================== */

  const renderAnalytics = () => {
    const analytics = [
      {
        name: "Landslide",
        value: 82,
        color: "#ef4444",
      },
      {
        name: "Flood",
        value: 68,
        color: "#eab308",
      },
      {
        name: "Earthquake",
        value: 54,
        color: "#f97316",
      },
      {
        name: "Forest Fire",
        value: 37,
        color: "#22c55e",
      },
    ];

    return (
      <>
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
          <MetricCard
            icon={ShieldAlert}
            label="Overall Risk"
            value={`${computedMetrics.overallRisk}`}
            detail="Composite score"
            tone="red"
          />

          <MetricCard
            icon={TrendingUp}
            label="Risk Trend"
            value="+8.4%"
            detail="Compared with previous cycle"
            tone="orange"
          />

          <MetricCard
            icon={Activity}
            label="Data Freshness"
            value="30s"
            detail="Automatic refresh interval"
            tone="emerald"
          />

          <MetricCard
            icon={Users}
            label="Coverage"
            value={
              computedMetrics.monitoredLocations
            }
            detail="Monitored points"
            tone="indigo"
          />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {/* Hazard analytics */}
          <section className="rounded-2xl border border-slate-800 bg-[#0d1420]/80 p-5">
            <SectionHeader
              title="Hazard Risk Distribution"
              subtitle="Current threat intensity by hazard"
              icon={TrendingUp}
            />

            <div className="space-y-5">
              {analytics.map((item) => (
                <div key={item.name}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-slate-300">
                      {item.name}
                    </span>

                    <span
                      className="text-xs font-bold"
                      style={{
                        color: item.color,
                      }}
                    >
                      {item.value}%
                    </span>
                  </div>

                  <div className="h-2 rounded-full bg-slate-900 overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{
                        width: `${item.value}%`,
                        backgroundColor:
                          item.color,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* District analytics */}
          <section className="rounded-2xl border border-slate-800 bg-[#0d1420]/80 p-5">
            <SectionHeader
              title="Regional Risk Ranking"
              subtitle="Highest monitored risk scores"
              icon={MapPin}
            />

            <div className="space-y-2">
              {[...districts]
                .sort(
                  (a, b) =>
                    Number(b.score) -
                    Number(a.score)
                )
                .slice(0, 7)
                .map((district, index) => {
                  const config =
                    getRiskConfig(
                      district.risk
                    );

                  return (
                    <button
                      key={district.id}
                      type="button"
                      onClick={() =>
                        handleDistrictSelect(
                          district
                        )
                      }
                      className="w-full flex items-center gap-3 p-3 rounded-xl bg-slate-950/30 hover:bg-slate-900/70 transition"
                    >
                      <span className="text-[10px] text-slate-700 w-4">
                        {String(
                          index + 1
                        ).padStart(2, "0")}
                      </span>

                      <div className="flex-1 text-left">
                        <div className="text-xs font-semibold text-slate-300">
                          {district.name}
                        </div>

                        <div className="mt-1 h-1 rounded-full bg-slate-900 overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${Math.min(
                                100,
                                Number(
                                  district.score
                                ) || 0
                              )}%`,
                              backgroundColor:
                                config.color,
                            }}
                          />
                        </div>
                      </div>

                      <span
                        className="text-xs font-black"
                        style={{
                          color: config.color,
                        }}
                      >
                        {district.score}
                      </span>
                    </button>
                  );
                })}
            </div>
          </section>
        </div>

        {/* Trend */}
        <section className="rounded-2xl border border-slate-800 bg-[#0d1420]/80 p-5">
          <SectionHeader
            title="24 Hour Risk Trend"
            subtitle="Composite regional intelligence signal"
            icon={Activity}
          />

          <div className="h-52 rounded-xl border border-slate-800 bg-[#080c13] relative overflow-hidden p-5">
            <div className="absolute inset-0 opacity-20 bg-[linear-gradient(to_right,#334155_1px,transparent_1px),linear-gradient(to_bottom,#334155_1px,transparent_1px)] [background-size:40px_40px]" />

            <svg
              viewBox="0 0 1000 240"
              preserveAspectRatio="none"
              className="relative w-full h-full"
            >
              <defs>
                <linearGradient
                  id="riskArea"
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="0%"
                    stopColor="#ef4444"
                    stopOpacity="0.28"
                  />

                  <stop
                    offset="100%"
                    stopColor="#ef4444"
                    stopOpacity="0"
                  />
                </linearGradient>
              </defs>

              <path
                d="M0,180 C100,160 120,170 200,145 C280,120 300,155 390,125 C470,95 510,130 600,95 C680,60 710,105 790,70 C860,40 920,75 1000,30 L1000,240 L0,240 Z"
                fill="url(#riskArea)"
              />

              <path
                d="M0,180 C100,160 120,170 200,145 C280,120 300,155 390,125 C470,95 510,130 600,95 C680,60 710,105 790,70 C860,40 920,75 1000,30"
                fill="none"
                stroke="#ef4444"
                strokeWidth="3"
              />
            </svg>

            <div className="absolute top-3 right-4 flex items-center gap-2 text-[9px] text-red-400">
              <TrendingUp className="w-3 h-3" />
              Elevated
            </div>
          </div>
        </section>
      </>
    );
  };

  /* =====================================================
     AI
  ===================================================== */

  const renderAI = () => {
    return (
      <div className="max-w-5xl mx-auto h-[calc(100vh-190px)] min-h-[600px]">
        <AIWorkspace
          aiQuery={aiQuery}
          setAiQuery={setAiQuery}
          aiResponse={aiResponse}
          isGenerating={isGenerating}
          onAsk={handleAiAsk}
        />
      </div>
    );
  };

  /* =====================================================
     MAIN RENDER
  ===================================================== */

  return (
    <div className="min-h-screen bg-[#070b12] text-slate-200 font-sans">
      {/* TOP HEADER */}
      <header className="sticky top-0 z-[1200] border-b border-slate-800/80 bg-[#080d15]/95 backdrop-blur-xl">
        <div className="max-w-[1800px] mx-auto px-4 md:px-6 h-[68px] flex items-center justify-between gap-4">
          {/* Brand */}
          <div className="flex items-center gap-3 shrink-0">
            <div className="relative w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
              <Radio className="w-5 h-5 text-indigo-400" />

              <span className="absolute -right-0.5 -top-0.5 w-2 h-2 rounded-full bg-emerald-400" />
            </div>

            <div className="hidden sm:block">
              <div className="text-sm font-black tracking-[0.14em] text-slate-100">
                DISASTER
              </div>

              <div className="text-[9px] font-semibold tracking-[0.24em] text-indigo-400">
                INTELLIGENCE
              </div>
            </div>
          </div>

          {/* Search */}
          <div
            ref={searchRef}
            className="relative flex-1 max-w-[520px] hidden md:block"
          >
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600" />

            <input
              value={searchQuery}
              onChange={(event) => {
                setSearchQuery(
                  event.target.value
                );
                setSearchOpen(true);
              }}
              onFocus={() =>
                setSearchOpen(true)
              }
              placeholder="Search district, locality or monitored area..."
              className="w-full h-10 rounded-xl border border-slate-800 bg-slate-950/60 pl-10 pr-20 text-xs text-slate-300 placeholder:text-slate-700 outline-none focus:border-indigo-500/40"
            />

            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[8px] text-slate-700 border border-slate-800 rounded px-1.5 py-0.5">
              SEARCH
            </span>

            {searchOpen &&
              searchQuery.trim() && (
                <SearchPanel
                  query={searchQuery}
                  setQuery={setSearchQuery}
                  districts={districts}
                  onSelect={
                    handleSearchSelect
                  }
                  onClose={() =>
                    setSearchOpen(false)
                  }
                />
              )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() =>
                setNotificationsOpen(
                  (value) => !value
                )
              }
              className="relative w-9 h-9 rounded-lg hover:bg-slate-800 flex items-center justify-center text-slate-500 hover:text-slate-200 transition"
            >
              <Bell className="w-4 h-4" />

              {alerts.length > 0 && (
                <span className="absolute right-1.5 top-1.5 w-1.5 h-1.5 rounded-full bg-red-500" />
              )}
            </button>

            <button
              type="button"
              onClick={() =>
                setProfileOpen(
                  (value) => !value
                )
              }
              className="flex items-center gap-2 ml-1 pl-2 border-l border-slate-800"
            >
              <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center">
                <User className="w-4 h-4 text-slate-400" />
              </div>

              <div className="hidden lg:block text-left">
                <div className="text-[10px] font-semibold text-slate-300 max-w-[110px] truncate">
                  {user?.name ||
                    user?.username ||
                    "Operator"}
                </div>

                <div className="text-[8px] text-emerald-400">
                  AUTHENTICATED
                </div>
              </div>

              <ChevronDown className="hidden lg:block w-3 h-3 text-slate-700" />
            </button>

            <button
              type="button"
              onClick={() =>
                setMobileMenuOpen(
                  (value) => !value
                )
              }
              className="md:hidden w-9 h-9 rounded-lg hover:bg-slate-800 flex items-center justify-center"
            >
              <Menu className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* DESKTOP NAV */}
        <div className="hidden md:block border-t border-slate-800/60">
          <div className="max-w-[1800px] mx-auto px-4 md:px-6 h-11 flex items-center gap-1">
            {TAB_CONFIG.map((tab) => {
              const Icon = tab.icon;
              const active =
                activeTab === tab.id;

              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() =>
                    navigateTab(tab.id)
                  }
                  className={`h-full px-4 flex items-center gap-2 text-[10px] font-semibold border-b-2 transition ${
                    active
                      ? "text-indigo-300 border-indigo-500"
                      : "text-slate-600 border-transparent hover:text-slate-300"
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {tab.id}
                </button>
              );
            })}

            <div className="ml-auto flex items-center gap-2 text-[9px] text-slate-600">
              <StatusDot
                active={!apiError}
              />

              {apiError
                ? "DEGRADED"
                : "SYSTEM OPERATIONAL"}
            </div>
          </div>
        </div>

        {/* MOBILE NAV */}
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-slate-800 bg-[#0a1019] p-2">
            {TAB_CONFIG.map((tab) => {
              const Icon = tab.icon;

              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() =>
                    navigateTab(tab.id)
                  }
                  className={`w-full px-3 py-3 rounded-lg flex items-center gap-3 text-xs ${
                    activeTab === tab.id
                      ? "bg-indigo-500/10 text-indigo-300"
                      : "text-slate-500"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {tab.id}
                </button>
              );
            })}
          </div>
        )}

        {/* Notification popover */}
        {notificationsOpen && (
          <div className="absolute right-4 top-[62px] w-[340px] rounded-2xl border border-slate-800 bg-[#0d1420]/98 backdrop-blur-xl shadow-2xl p-3">
            <div className="flex items-center justify-between px-2 pb-2">
              <span className="text-xs font-bold text-slate-200">
                Notifications
              </span>

              <button
                type="button"
                onClick={() =>
                  setNotificationsOpen(
                    false
                  )
                }
                className="text-slate-600 hover:text-slate-300"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            <AlertPanel
              alerts={alerts.slice(0, 4)}
              onAlertClick={(alert) => {
                setSelectedAlert(alert);
                setNotificationsOpen(
                  false
                );
                setActiveTab(
                  "Live Monitoring"
                );
              }}
            />
          </div>
        )}

        {/* Profile popover */}
        {profileOpen && (
          <div className="absolute right-4 top-[62px] w-64 rounded-2xl border border-slate-800 bg-[#0d1420]/98 backdrop-blur-xl shadow-2xl p-3">
            <div className="p-3 border-b border-slate-800">
              <div className="text-xs font-semibold text-slate-200">
                {user?.name ||
                  user?.username ||
                  "Operator"}
              </div>

              <div className="text-[10px] text-slate-600 mt-1">
                {user?.email ||
                  "Authenticated operator"}
              </div>
            </div>

            <button
              type="button"
              onClick={logout}
              className="w-full mt-2 px-3 py-2.5 rounded-lg hover:bg-red-500/10 text-left text-[10px] text-red-400 flex items-center gap-2"
            >
              <LogOut className="w-3.5 h-3.5" />
              Sign out
            </button>
          </div>
        )}
      </header>

      {/* MAIN */}
      <main className="max-w-[1800px] mx-auto px-4 md:px-6 py-5">
        {/* PAGE TITLE */}
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 mb-5">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <StatusDot
                active={!apiError}
              />

              <span className="text-[9px] uppercase tracking-[0.2em] text-emerald-400">
                {apiError
                  ? "Intelligence service degraded"
                  : "System operational"}
              </span>
            </div>

            <h1 className="text-xl md:text-2xl font-black tracking-tight text-slate-100">
              Uttarakhand Disaster Intelligence
            </h1>

            <p className="text-[11px] text-slate-600 mt-1">
              Live monitoring, geospatial risk
              analytics and AI-assisted disaster
              intelligence.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <div className="hidden sm:flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/30 px-3 py-2">
              <RefreshCw
                className={`w-3.5 h-3.5 text-slate-600 ${
                  refreshing
                    ? "animate-spin"
                    : ""
                }`}
              />

              <span className="text-[9px] text-slate-600">
                Sync{" "}
                {lastSync.toLocaleTimeString()}
              </span>
            </div>

            <button
              type="button"
              onClick={() =>
                loadDashboard(true)
              }
              className="h-9 px-3 rounded-xl border border-slate-800 bg-slate-950/40 hover:bg-slate-900 text-[10px] text-slate-400 flex items-center gap-2"
            >
              <RefreshCw
                className={`w-3.5 h-3.5 ${
                  refreshing
                    ? "animate-spin"
                    : ""
                }`}
              />
              Refresh
            </button>
          </div>
        </div>

        {/* API WARNING */}
        {apiError && (
          <div className="mb-4 rounded-xl border border-yellow-500/20 bg-yellow-500/[0.04] px-4 py-3 flex items-start gap-3">
            <AlertTriangle className="w-4 h-4 text-yellow-400 mt-0.5" />

            <div>
              <div className="text-xs font-semibold text-yellow-300">
                Intelligence API unavailable
              </div>

              <div className="text-[10px] text-slate-500 mt-1">
                {apiError}
              </div>
            </div>
          </div>
        )}

        {/* VIEW */}
        <div className="space-y-4">
          {activeTab === "Dashboard" &&
            renderDashboard()}

          {activeTab ===
            "Live Monitoring" &&
            renderLiveMonitoring()}

          {activeTab ===
            "Risk Analytics" &&
            renderAnalytics()}

          {activeTab ===
            "AI Intelligence" &&
            renderAI()}
        </div>

        {/* FOOTER */}
        <footer className="mt-8 pt-4 border-t border-slate-900 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="text-[9px] text-slate-700">
            DISASTER INTELLIGENCE • UTTARAKHAND
          </div>

          <div className="flex items-center gap-3 text-[9px] text-slate-700">
            <span>React</span>
            <span>•</span>
            <span>FastAPI</span>
            <span>•</span>
            <span>Leaflet</span>
            <span>•</span>
            <span>Groq AI</span>
          </div>
        </footer>
      </main>

      {/* ALERT DETAIL MODAL */}
      {selectedAlert && (
        <div className="fixed inset-0 z-[2000] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-lg rounded-2xl border border-slate-800 bg-[#0d1420] shadow-2xl overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <AlertOctagon className="w-5 h-5 text-red-400" />

                <div>
                  <div className="text-xs font-bold text-slate-200">
                    Alert Intelligence
                  </div>

                  <div className="text-[9px] text-slate-600 mt-0.5">
                    {selectedAlert.location}
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={() =>
                  setSelectedAlert(null)
                }
                className="text-slate-600 hover:text-slate-300"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5">
              <RiskBadge
                risk={
                  selectedAlert.severity ===
                  "CRITICAL"
                    ? "CRITICAL"
                    : selectedAlert.severity ===
                      "WARNING"
                    ? "MEDIUM"
                    : "LOW"
                }
              />

              <h3 className="text-base font-bold text-slate-100 mt-4">
                {selectedAlert.title}
              </h3>

              <p className="text-xs leading-6 text-slate-500 mt-2">
                {selectedAlert.description}
              </p>

              <div className="grid grid-cols-2 gap-3 mt-5">
                <div className="rounded-xl border border-slate-800 bg-slate-950/30 p-3">
                  <div className="text-[9px] uppercase text-slate-600">
                    Location
                  </div>

                  <div className="text-xs text-slate-300 mt-1">
                    {selectedAlert.location}
                  </div>
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-950/30 p-3">
                  <div className="text-[9px] uppercase text-slate-600">
                    Received
                  </div>

                  <div className="text-xs text-slate-300 mt-1">
                    {formatRelativeTime(
                      selectedAlert.timestamp
                    )}
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={() => {
                  const match =
                    districts.find(
                      (district) =>
                        district.name
                          .toLowerCase() ===
                        String(
                          selectedAlert.location
                        ).toLowerCase()
                    );

                  if (match) {
                    handleDistrictSelect(
                      match
                    );
                  }

                  setSelectedAlert(null);
                }}
                className="w-full mt-4 h-10 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold flex items-center justify-center gap-2"
              >
                <Crosshair className="w-3.5 h-3.5" />
                Locate on live map
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}