// src/disaster/emergencyResources.js

export const RESOURCE_TYPES = {
  SHELTER: "SHELTER",
  HOSPITAL: "HOSPITAL",
  POLICE: "POLICE",
  FIRE_STATION: "FIRE_STATION",
  AMBULANCE: "AMBULANCE",
  RELIEF_CENTER: "RELIEF_CENTER",
};

export const getResourceIcon = (type) => {
  switch (type) {
    case RESOURCE_TYPES.SHELTER:
      return "🏠";

    case RESOURCE_TYPES.HOSPITAL:
      return "🏥";

    case RESOURCE_TYPES.POLICE:
      return "🚓";

    case RESOURCE_TYPES.FIRE_STATION:
      return "🚒";

    case RESOURCE_TYPES.AMBULANCE:
      return "🚑";

    case RESOURCE_TYPES.RELIEF_CENTER:
      return "📦";

    default:
      return "📍";
  }
};

export const normalizeResource = (resource) => {
  return {
    id: resource.id,

    name: resource.name || "Emergency Resource",

    type: resource.type || RESOURCE_TYPES.RELIEF_CENTER,

    latitude:
      Number(resource.latitude ?? resource.lat) || null,

    longitude:
      Number(resource.longitude ?? resource.lng) || null,

    address: resource.address || "",

    phone: resource.phone || "",

    available:
      resource.available !== false,
  };
};