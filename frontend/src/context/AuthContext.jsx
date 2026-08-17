import {
  createContext,
  useContext,
  useEffect,
  useState,
} from "react";

import { apiRequest } from "../services/api";

const AuthContext = createContext(null);

const TOKEN_KEY = "disaster_access_token";
const USER_KEY = "disaster_user";

export function AuthProvider({ children }) {
  // =====================================================
  // RESTORE USER
  // =====================================================

  const [user, setUser] = useState(() => {
    try {
      const savedUser =
        localStorage.getItem(USER_KEY);

      return savedUser
        ? JSON.parse(savedUser)
        : null;
    } catch {
      localStorage.removeItem(USER_KEY);
      return null;
    }
  });

  const [loading, setLoading] = useState(true);

  // =====================================================
  // RESTORE SESSION
  // =====================================================

  useEffect(() => {
    const token =
      localStorage.getItem(TOKEN_KEY);

    if (token) {
      try {
        const savedUser =
          localStorage.getItem(USER_KEY);

        if (savedUser) {
          setUser(JSON.parse(savedUser));
        }
      } catch (error) {
        console.error(
          "Failed to restore user:",
          error
        );

        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);

        setUser(null);
      }
    }

    setLoading(false);

    // ===================================================
    // HANDLE EXPIRED SESSION
    // ===================================================

    const handleLogout = () => {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);

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

  // =====================================================
  // REGISTER
  // =====================================================

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

  // =====================================================
  // LOGIN
  // =====================================================

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

    // ===================================================
    // CHECK TOKEN
    // ===================================================

    if (!data?.access_token) {
      throw new Error(
        "Authentication token was not received."
      );
    }

    // ===================================================
    // SAVE TOKEN
    // ===================================================

    localStorage.setItem(
      TOKEN_KEY,
      data.access_token
    );

    // ===================================================
    // SAVE USER
    // ===================================================

    if (data.user) {
      localStorage.setItem(
        USER_KEY,
        JSON.stringify(data.user)
      );

      setUser(data.user);
    }

    return data;
  }

  // =====================================================
  // LOGOUT
  // =====================================================

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);

    setUser(null);
  }

  // =====================================================
  // CONTEXT VALUE
  // =====================================================

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

// =========================================================
// USE AUTH
// =========================================================

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error(
      "useAuth must be used inside AuthProvider"
    );
  }

  return context;
}