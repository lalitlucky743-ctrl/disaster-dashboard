// src/disaster/disasterContext.js

export const buildDisasterContext = ({
  location,
  weather,
  risks,
  alerts = [],
  recommendations = [],
}) => {
  const activeAlerts = alerts.filter(
    (alert) =>
      alert &&
      alert.status !== "expired" &&
      alert.status !== "inactive"
  );

  return {
    location: {
      name: location?.name || "Unknown",
      latitude: location?.latitude ?? null,
      longitude: location?.longitude ?? null,
    },

    weather: {
      temperature: weather?.temperature ?? null,
      rainfall: weather?.rainfall ?? null,
      humidity: weather?.humidity ?? null,
      windSpeed: weather?.windSpeed ?? null,
    },

    risk: {
      overall: risks?.overall ?? null,

      flood: risks?.flood ?? null,

      landslide: risks?.landslide ?? null,

      rainfall: risks?.rainfall ?? null,

      heat: risks?.heat ?? null,
    },

    officialAlerts: activeAlerts.map((alert) => ({
      title: alert.title,
      description: alert.description,
      severity: alert.severity,
      source: alert.source,
      issuedAt: alert.issuedAt,
      expiresAt: alert.expiresAt,
    })),

    recommendations,
  };
};