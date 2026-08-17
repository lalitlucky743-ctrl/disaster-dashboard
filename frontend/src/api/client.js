const API_BASE_URL =
  import.meta.env.VITE_API_URL ||
  "https://disaster-dashboard-9qr8.onrender.com";

/* =========================================================
   TOKEN HELPERS
========================================================= */

function getAccessToken() {
  // Support both possible token keys
  return (
    localStorage.getItem("access_token") ||
    localStorage.getItem("disaster_access_token")
  );
}

function clearAuth() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("disaster_access_token");
  localStorage.removeItem("user");

  window.dispatchEvent(new Event("auth-expired"));
}

/* =========================================================
   API REQUEST
========================================================= */

async function request(endpoint, options = {}) {
  const token = getAccessToken();

  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  // Attach JWT
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
    throw new Error(
      "Unable to connect to the Disaster Intelligence backend."
    );
  }

  /* =======================================================
     RESPONSE PARSING
  ======================================================= */

  let data = null;

  const contentType =
    response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  } else {
    try {
      const text = await response.text();
      data = text || null;
    } catch {
      data = null;
    }
  }

  /* =======================================================
     AUTH ERRORS
  ======================================================= */

  if (response.status === 401) {
    clearAuth();

    throw new Error("SESSION_EXPIRED");
  }

  if (response.status === 403) {
    /*
      Backend can return 403 when:
      - JWT is invalid
      - JWT is missing
      - User doesn't have permission
      - Token cannot be decoded
    */

    const message =
      typeof data === "string"
        ? data
        : data?.detail ||
          data?.message ||
          "Access forbidden. Please sign in again.";

    throw new Error(message);
  }

  /* =======================================================
     OTHER API ERRORS
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
   API
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

export { API_BASE_URL };