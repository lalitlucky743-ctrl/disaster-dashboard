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

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const savedUser = localStorage.getItem(USER_KEY);
      const token = localStorage.getItem(TOKEN_KEY);

      // Restore the user only when both token and user exist.
      return token && savedUser ? JSON.parse(savedUser) : null;
    } catch (error) {
      console.error("Failed to restore saved user:", error);
      localStorage.removeItem(USER_KEY);
      localStorage.removeItem(TOKEN_KEY);
      return null;
    }
  });

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    function restoreSession() {
      try {
        const token = localStorage.getItem(TOKEN_KEY);
        const savedUser = localStorage.getItem(USER_KEY);

        if (token && savedUser) {
          setUser(JSON.parse(savedUser));
        } else {
          setUser(null);

          if (!token) {
            localStorage.removeItem(USER_KEY);
          }
        }
      } catch (error) {
        console.error("Failed to restore authentication:", error);
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        setUser(null);
      } finally {
        setLoading(false);
      }
    }

    function handleLogout() {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      localStorage.removeItem("access_token");
      localStorage.removeItem("user");
      setUser(null);
    }

    restoreSession();

    window.addEventListener("auth:logout", handleLogout);

    return () => {
      window.removeEventListener("auth:logout", handleLogout);
    };
  }, []);

  async function register(name, email, password) {
    return apiRequest("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        name: name.trim(),
        email: email.trim().toLowerCase(),
        password,
      }),
    });
  }

  // Direct login using email and password.
  async function login(email, password) {
    const normalizedEmail = email.trim().toLowerCase();

    const data = await apiRequest("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: normalizedEmail,
        password,
      }),
    });

    // The backend must return both an access token and user details.
    if (!data?.access_token || !data?.user) {
      throw new Error(
        "Login failed: the server did not return a valid authentication session."
      );
    }

    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(USER_KEY, JSON.stringify(data.user));

    setUser(data.user);

    return data;
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");

    setUser(null);

    window.dispatchEvent(new Event("auth:logout"));
  }

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

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }

  return context;
}