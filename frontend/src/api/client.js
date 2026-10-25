const API_BASE_URL =
  import.meta.env.VITE_API_URL ||
  "https://disaster-dashboard-kgbb.onrender.com";

/* =========================================================
   TOKEN HELPERS
========================================================= */

function getAccessToken() {
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
   API REQUEST CONFIGURATION
========================================================= */

const REQUEST_TIMEOUT_MS = 45000;

async function fetchWithTimeout(
  url,
  options,
  timeout = REQUEST_TIMEOUT_MS
) {
  const controller = new AbortController();

  const timer = setTimeout(() => {
    controller.abort();
  }, timeout);

  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

/* =========================================================
   MAIN REQUEST HANDLER
========================================================= */

async function request(endpoint, options = {}) {
  // Custom timeout is handled separately; it must not be passed to fetch.
  const {
    timeoutMs = REQUEST_TIMEOUT_MS,
    ...requestOptions
  } = options;

  const requestTimeout =
    Number.isFinite(timeoutMs) && timeoutMs > 0
      ? timeoutMs
      : REQUEST_TIMEOUT_MS;

  const token = getAccessToken();

  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
    ...(requestOptions.headers || {}),
  };

  // Attach JWT when available.
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let response;
  let attempt = 0;
  const maxAttempts = 2;

  while (attempt < maxAttempts) {
    attempt += 1;

    try {
      const method = requestOptions.method || "GET";

      console.log(
        `📡 API request (attempt ${attempt}/${maxAttempts}): ${method} ${endpoint}`
      );

      response = await fetchWithTimeout(
        `${API_BASE_URL}${endpoint}`,
        {
          ...requestOptions,
          headers,
        },
        requestTimeout
      );

      break;
    } catch (error) {
      const isTimeout = error?.name === "AbortError";

      console.warn(
        `⚠️ API request failed (attempt ${attempt}/${maxAttempts}): ${endpoint}`,
        isTimeout
          ? "Timed out; backend may be starting or processing a long request."
          : error
      );

      if (attempt >= maxAttempts) {
        throw new Error(
          isTimeout
            ? "The backend took too long to respond. Please try again."
            : "Unable to connect to the Disaster Intelligence backend."
        );
      }
    }
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

    console.error(
      `❌ API error ${response.status} on ${endpoint}:`,
      data
    );

    throw new Error(message);
  }

  console.log(`✅ API success: ${endpoint}`, data);

  return data;
}

/* =========================================================
   EXPORTED API METHODS
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