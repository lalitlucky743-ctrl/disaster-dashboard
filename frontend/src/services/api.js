const API_BASE_URL = (
  import.meta.env.VITE_API_URL ||
  "https://disaster-dashboard-kgbb.onrender.com"
).replace(/\/$/, "");

const TOKEN_KEY = "disaster_access_token";
const USER_KEY = "disaster_user";


function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY);
}


function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);

  localStorage.removeItem("access_token");
  localStorage.removeItem("user");

  window.dispatchEvent(new Event("auth:logout"));
}


function isPublicAuthEndpoint(endpoint) {
  return [
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/verify-otp",
    "/api/auth/resend-otp",
  ].some(
    (path) =>
      endpoint === path ||
      endpoint.startsWith(`${path}?`)
  );
}


async function request(endpoint, options = {}) {
  const token = getAccessToken();
  const publicAuthEndpoint = isPublicAuthEndpoint(endpoint);

  const headers = {
    Accept: "application/json",

    ...(options.body
      ? { "Content-Type": "application/json" }
      : {}),

    ...(options.headers || {}),
  };

  // Don't attach an existing JWT to public login or OTP requests.
  if (token && !publicAuthEndpoint) {
    headers.Authorization = `Bearer ${token}`;
  }

  let response;

  try {
    response = await fetch(
      `${API_BASE_URL}${endpoint}`,
      {
        ...options,
        headers,
      }
    );
  } catch (error) {
    console.error("API connection error:", error);

    throw new Error(
      "Unable to connect to the Disaster Intelligence backend."
    );
  }

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

  // A 401 from a protected endpoint expires the session.
  // Login/OTP errors should preserve their own error messages.
  if (
    response.status === 401 &&
    token &&
    !publicAuthEndpoint
  ) {
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


export async function apiRequest(endpoint, options = {}) {
  return request(endpoint, options);
}


export {
  API_BASE_URL,
  getAccessToken,
  clearAuth,
  TOKEN_KEY,
  USER_KEY,
};