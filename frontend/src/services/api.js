const API_BASE_URL =
  import.meta.env.VITE_API_URL ||
  "https://disaster-dashboard-9qr8.onrender.com";

/* =========================================================
   STORAGE KEYS
========================================================= */

const TOKEN_KEY = "disaster_access_token";
const USER_KEY = "disaster_user";

/* =========================================================
   TOKEN HELPERS
========================================================= */

function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);

  // Compatibility cleanup
  localStorage.removeItem("access_token");
  localStorage.removeItem("user");

  window.dispatchEvent(new Event("auth:logout"));
}

/* =========================================================
   API REQUEST
========================================================= */

async function request(endpoint, options = {}) {
  const token = getAccessToken();

  const headers = {
    Accept: "application/json",
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {}),
  };

  /* =======================================================
     ATTACH JWT
  ======================================================= */

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let response;

  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers,
    });
  } catch (error) {
    console.error("API connection error:", error);

    throw new Error(
      "Unable to connect to the Disaster Intelligence backend."
    );
  }

  /* =======================================================
     PARSE RESPONSE
  ======================================================= */

  let data = null;

  const contentType =
    response.headers.get("content-type") || "";

  try {
    if (contentType.includes("application/json")) {
      data = await response.json();
    } else {
      const text = await response.text();
      data = text || null;
    }
  } catch {
    data = null;
  }

  /* =======================================================
     401 UNAUTHORIZED
  ======================================================= */

  if (response.status === 401) {
    clearAuth();

    throw new Error("SESSION_EXPIRED");
  }

  /* =======================================================
     403 FORBIDDEN
  ======================================================= */

  if (response.status === 403) {
    const message =
      typeof data === "string"
        ? data
        : data?.detail ||
          data?.message ||
          "Access forbidden. Please sign in again.";

    throw new Error(message);
  }

  /* =======================================================
     OTHER ERRORS
  ======================================================= */

  if (!response.ok) {
    const message =
      typeof data === "string"
        ? data
        : data?.detail ||
          data?.message ||
          `Request failed with status ${response.status}`;

    throw new Error(message);
  }

  return data;
}

/* =========================================================
   API METHODS
========================================================= */

export const api = {
  get(endpoint, options = {}) {
    return request(endpoint, {
      ...options,
      method: "GET",
    });
  },

  post(endpoint, body, options = {}) {
    return request(endpoint, {
      ...options,
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  put(endpoint, body, options = {}) {
    return request(endpoint, {
      ...options,
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  delete(endpoint, options = {}) {
    return request(endpoint, {
      ...options,
      method: "DELETE",
    });
  },
};

/* =========================================================
   apiRequest
   Compatibility function for AuthContext
========================================================= */

export async function apiRequest(endpoint, options = {}) {
  return request(endpoint, options);
}

/* =========================================================
   EXPORTS
========================================================= */

export {
  API_BASE_URL,
  getAccessToken,
  clearAuth,
  TOKEN_KEY,
  USER_KEY,
};