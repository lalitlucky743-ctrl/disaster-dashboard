import {
  createContext,
  useContext,
  useEffect,
  useState,
} from "react";

import {
  apiRequest,
  TOKEN_KEY,
  USER_KEY,
} from "../services/api";

/* =========================================================
   AUTH CONTEXT
========================================================= */

const AuthContext = createContext(null);

/* =========================================================
   AUTH PROVIDER
========================================================= */

export function AuthProvider({ children }) {
  /* =======================================================
     RESTORE USER
  ======================================================= */

  const [user, setUser] = useState(() => {
    try {
      const savedUser =
        localStorage.getItem(USER_KEY);

      return savedUser
        ? JSON.parse(savedUser)
        : null;
    } catch (error) {
      console.error(
        "Failed to restore saved user:",
        error
      );

      localStorage.removeItem(USER_KEY);

      return null;
    }
  });

  const [loading, setLoading] = useState(true);

  /* =======================================================
     RESTORE SESSION
  ======================================================= */

  useEffect(() => {
    try {
      const token =
        localStorage.getItem(TOKEN_KEY);

      const savedUser =
        localStorage.getItem(USER_KEY);

      if (token && savedUser) {
        setUser(JSON.parse(savedUser));
      } else if (!token) {
        // No token = no authenticated session
        setUser(null);
        localStorage.removeItem(USER_KEY);
      }
    } catch (error) {
      console.error(
        "Failed to restore authentication:",
        error
      );

      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);

      setUser(null);
    }

    setLoading(false);

    /* =====================================================
       HANDLE AUTH LOGOUT / SESSION EXPIRY
    ===================================================== */

    const handleLogout = () => {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);

      // Compatibility cleanup
      localStorage.removeItem("access_token");
      localStorage.removeItem("user");

      setUser(null);
    };

    window.addEventListener(
      "auth:logout",
      handleLogout
    );

    return () => {
      window.removeEventListener(
        "auth:logout",
        handleLogout
      );
    };
  }, []);

  /* =========================================================
     REGISTER
  ========================================================= */

  async function register(
    name,
    email,
    password
  ) {
    const data = await apiRequest(
      "/api/auth/register",
      {
        method: "POST",
        body: JSON.stringify({
          name,
          email,
          password,
        }),
      }
    );

    return data;
  }

  /* =========================================================
     LOGIN
  ========================================================= */

  async function login(
    email,
    password
  ) {
    const data = await apiRequest(
      "/api/auth/login",
      {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
        }),
      }
    );

    /* =====================================================
       CHECK TOKEN
    ===================================================== */

    if (!data?.access_token) {
      throw new Error(
        "Authentication token was not received."
      );
    }

    /* =====================================================
       SAVE TOKEN
    ===================================================== */

    localStorage.setItem(
      TOKEN_KEY,
      data.access_token
    );

    /* =====================================================
       SAVE USER
    ===================================================== */

    if (data.user) {
      localStorage.setItem(
        USER_KEY,
        JSON.stringify(data.user)
      );

      setUser(data.user);
    } else {
      // Even if backend doesn't return user,
      // token is still saved.
      setUser(null);
    }

    return data;
  }

  /* =========================================================
     LOGOUT
  ========================================================= */

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);

    // Compatibility cleanup
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");

    setUser(null);

    window.dispatchEvent(
      new Event("auth:logout")
    );
  }

  /* =========================================================
     CONTEXT VALUE
  ========================================================= */

  const value = {
    user,
    loading,
    register,
    login,
    logout,
    isAuthenticated: Boolean(user),
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

/* =========================================================
   USE AUTH
========================================================= */

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error(
      "useAuth must be used inside AuthProvider"
    );
  }

  return context;
}