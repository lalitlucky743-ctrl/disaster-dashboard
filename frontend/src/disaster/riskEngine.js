// src/disaster/riskEngine.js

const clamp = (value, min = 0, max = 100) => {
  return Math.min(max, Math.max(min, Number(value) || 0));
};

export const getRiskLevel = (score) => {
  const value = clamp(score);

  if (value < 25) return "LOW";
  if (value < 50) return "MODERATE";
  if (value < 75) return "HIGH";
  return "CRITICAL";
};

export const getRiskColor = (score) => {
  const level = getRiskLevel(score);

  switch (level) {
    case "LOW":
      return "#22c55e";

    case "MODERATE":
      return "#eab308";

    case "HIGH":
      return "#f97316";

    case "CRITICAL":
      return "#ef4444";

    default:
      return "#64748b";
  }
};

/**
 * Flood risk calculation.
 *
 * IMPORTANT:
 * These are initial engineering weights.
 * They should later be calibrated against historical disaster data.
 */
export const calculateFloodRisk = ({
  rainfall24h = 0,
  rainfallIntensity = 0,
  riverLevel = 0,
  terrainRisk = 0,
  historicalRisk = 0,
  vulnerability = 0,
  mlScore = 0,
}) => {
  const rainfallScore = clamp(rainfall24h);
  const intensityScore = clamp(rainfallIntensity);
  const riverScore = clamp(riverLevel);
  const terrainScore = clamp(terrainRisk);
  const historicalScore = clamp(historicalRisk);
  const vulnerabilityScore = clamp(vulnerability);
  const machineLearningScore = clamp(mlScore);

  const score =
    rainfallScore * 0.20 +
    intensityScore * 0.20 +
    riverScore * 0.20 +
    terrainScore * 0.10 +
    historicalScore * 0.10 +
    vulnerabilityScore * 0.05 +
    machineLearningScore * 0.15;

  const finalScore = Math.round(clamp(score));

  return {
    score: finalScore,
    level: getRiskLevel(finalScore),
    color: getRiskColor(finalScore),

    factors: {
      rainfall: rainfallScore,
      rainfallIntensity: intensityScore,
      river: riverScore,
      terrain: terrainScore,
      historical: historicalScore,
      vulnerability: vulnerabilityScore,
      ml: machineLearningScore,
    },
  };
};

export const calculateLandslideRisk = ({
  rainfallIntensity = 0,
  previousRainfall = 0,
  slopeRisk = 0,
  terrainRisk = 0,
  historicalRisk = 0,
  vulnerability = 0,
  mlScore = 0,
}) => {
  const score =
    clamp(rainfallIntensity) * 0.25 +
    clamp(previousRainfall) * 0.15 +
    clamp(slopeRisk) * 0.20 +
    clamp(terrainRisk) * 0.15 +
    clamp(historicalRisk) * 0.10 +
    clamp(vulnerability) * 0.05 +
    clamp(mlScore) * 0.10;

  const finalScore = Math.round(clamp(score));

  return {
    score: finalScore,
    level: getRiskLevel(finalScore),
    color: getRiskColor(finalScore),

    factors: {
      rainfallIntensity: clamp(rainfallIntensity),
      previousRainfall: clamp(previousRainfall),
      slope: clamp(slopeRisk),
      terrain: clamp(terrainRisk),
      historical: clamp(historicalRisk),
      vulnerability: clamp(vulnerability),
      ml: clamp(mlScore),
    },
  };
};

export const calculateOverallRisk = ({
  flood = 0,
  landslide = 0,
  rainfall = 0,
  heat = 0,
}) => {
  const score = Math.round(
    clamp(flood) * 0.35 +
      clamp(landslide) * 0.35 +
      clamp(rainfall) * 0.20 +
      clamp(heat) * 0.10
  );

  return {
    score,
    level: getRiskLevel(score),
    color: getRiskColor(score),
  };
};