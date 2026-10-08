// src/disaster/riskRecommendations.js

export const getRiskRecommendations = ({
  flood = 0,
  landslide = 0,
  rainfall = 0,
}) => {
  const recommendations = [];

  if (flood >= 75) {
    recommendations.push({
      type: "FLOOD",
      priority: "HIGH",
      title: "Flood risk is high",
      message:
        "Avoid unnecessary travel through low-lying or flood-prone areas and monitor official disaster alerts.",
    });
  } else if (flood >= 50) {
    recommendations.push({
      type: "FLOOD",
      priority: "MEDIUM",
      title: "Elevated flood risk",
      message:
        "Stay updated with local alerts and avoid areas near overflowing drains, streams or rivers.",
    });
  }

  if (landslide >= 75) {
    recommendations.push({
      type: "LANDSLIDE",
      priority: "HIGH",
      title: "High landslide risk",
      message:
        "Avoid unnecessary travel near steep slopes and unstable terrain, especially during heavy rainfall.",
    });
  } else if (landslide >= 50) {
    recommendations.push({
      type: "LANDSLIDE",
      priority: "MEDIUM",
      title: "Elevated landslide risk",
      message:
        "Exercise caution around steep slopes and monitor official local warnings.",
    });
  }

  if (rainfall >= 75) {
    recommendations.push({
      type: "RAINFALL",
      priority: "HIGH",
      title: "Heavy rainfall detected",
      message:
        "Heavy rainfall can increase flash-flood and landslide risk. Stay indoors where appropriate and monitor official alerts.",
    });
  }

  if (recommendations.length === 0) {
    recommendations.push({
      type: "GENERAL",
      priority: "LOW",
      title: "No major calculated risk",
      message:
        "Continue monitoring weather conditions and official disaster alerts.",
    });
  }

  return recommendations;
};