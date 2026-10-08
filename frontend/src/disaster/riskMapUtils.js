// src/disaster/riskMapUtils.js

import { getRiskColor, getRiskLevel } from "./riskEngine";

export const createRiskPopup = ({
  location,
  flood = 0,
  landslide = 0,
  rainfall = 0,
}) => {
  const overall = Math.max(flood, landslide, rainfall);

  return `
    <div style="min-width:220px">
      <h3 style="margin:0 0 8px 0">
        ${location || "Unknown Location"}
      </h3>

      <div style="margin-bottom:5px">
        <strong>Overall Risk:</strong>
        <span style="
          color:${getRiskColor(overall)};
          font-weight:700;
        ">
          ${getRiskLevel(overall)}
        </span>
      </div>

      <div>🌊 Flood: ${Math.round(flood)}%</div>
      <div>⛰️ Landslide: ${Math.round(landslide)}%</div>
      <div>🌧️ Rainfall Risk: ${Math.round(rainfall)}%</div>
    </div>
  `;
};

export const getRiskZoneStyle = (score) => {
  return {
    color: getRiskColor(score),
    fillColor: getRiskColor(score),
    fillOpacity: 0.35,
    weight: 2,
  };
};

export const getRiskMarkerStyle = (score) => {
  return {
    color: getRiskColor(score),
    fillColor: getRiskColor(score),
    fillOpacity: 0.85,
    radius: score >= 75 ? 10 : score >= 50 ? 8 : 6,
  };
};