const API_BASE_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const TOKEN_KEY = "disaster_access_token";

async function apiRequest(endpoint, options = {}) {
  const token = localStorage.getItem(TOKEN_KEY);

  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(
    `${API_BASE_URL}${endpoint}`,
    {
      ...options,
      headers,
    }
  );

  let data = null;

  try {
    data = await response.json();
  } catch {
    data = null;
  }

  // =====================================================
  // SESSION / AUTH ERROR
  // =====================================================

  if (response.status === 401 || response.status === 403) {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem("disaster_user");

    window.dispatchEvent(
      new Event("auth:logout")
    );

    throw new Error("SESSION_EXPIRED");
  }

  // =====================================================
  // OTHER ERRORS
  // =====================================================

  if (!response.ok) {
    throw new Error(
      data?.detail ||
      data?.message ||
      `Request failed with status ${response.status}`
    );
  }

  return data;
}

// =========================================================
// GET
// =========================================================

function get(endpoint) {
  return apiRequest(endpoint, {
    method: "GET",
  });
}

// =========================================================
// POST
// =========================================================

function post(endpoint, body) {
  return apiRequest(endpoint, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// =========================================================
// PUT
// =========================================================

function put(endpoint, body) {
  return apiRequest(endpoint, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// =========================================================
// DELETE
// =========================================================

function remove(endpoint) {
  return apiRequest(endpoint, {
    method: "DELETE",
  });
}

export {
  apiRequest,
  get,
  post,
  put,
  remove,
  API_BASE_URL,
};