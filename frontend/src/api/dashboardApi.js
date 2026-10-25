import { api } from "./client";

export const dashboardApi = {
  getOverview() {
    return api.get("/api/dashboard/overview");
  },

  getAlerts() {
    return api.get("/api/dashboard/alerts");
  },

  getDistricts() {
    return api.get("/api/dashboard/districts");
  },

  getDistrictLocations(districtId) {
    return api.get(`/api/dashboard/districts/${districtId}/locations`);
  },

  getRiskZones() {
    return api.get("/api/dashboard/risk-zones");
  },

  getLiveMonitoring() {
    return api.get("/api/monitoring/live");
  },

  getAutomaticMonitoringStatus() {
    return api.get("/api/monitoring/status");
  },

  getAutomaticMonitoringHistory(limit = 10) {
    return api.get(
      `/api/monitoring/history?limit=${encodeURIComponent(limit)}`
    );
  },

  runAutomaticMonitoringOnce() {
    return api.post("/api/monitoring/run-once", {}, { timeoutMs: 180000 });
  },

  getAnalytics() {
    return api.get("/api/analytics/overview");
  },

  getWeather(location) {
    return api.get(`/api/weather/${encodeURIComponent(location)}`);
  },
};