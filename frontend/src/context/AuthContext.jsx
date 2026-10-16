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
      return savedUser ? JSON.parse(savedUser) : null;
    } catch (error) {
      console.error("Failed to restore saved user:", error);
      localStorage.removeItem(USER_KEY);
      return null;
    }
  });

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    try {
      const token = localStorage.getItem(TOKEN_KEY);
      const savedUser = localStorage.getItem(USER_KEY);
      if (token && savedUser) {
        setUser(JSON.parse(savedUser));
      } else {
        setUser(null);
        if (!token) localStorage.removeItem(USER_KEY);
      }
    } catch (error) {
      console.error("Failed to restore authentication:", error);
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      setUser(null);
    }

    setLoading(false);

    const handleLogout = () => {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      localStorage.removeItem("access_token");
      localStorage.removeItem("user");
      setUser(null);
    };

    window.addEventListener("auth:logout", handleLogout);
    return () => window.removeEventListener("auth:logout", handleLogout);
  }, []);

  async function register(name, email, password) {
    return apiRequest("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    });
  }

  // Step 1: password verification sends an OTP challenge; it must NOT save a JWT.
  async function login(email, password) {
    const data = await apiRequest("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });

    if (data?.otp_required !== true || !data?.challenge_id) {
      throw new Error(
        "OTP verification was not started. Deploy the updated backend and configure email delivery before signing in."
      );
    }

    return data;
  }

  // Step 2: save authentication only when the backend returns a token after OTP verification.
  async function verifyLoginOtp(challengeId, otp) {
    const data = await apiRequest("/api/auth/verify-otp", {
      method: "POST",
      body: JSON.stringify({ challenge_id: challengeId, otp }),
    });

    if (!data?.access_token || !data?.user) {
      throw new Error("The server did not return an authenticated session.");
    }

    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    setUser(data.user);
    return data;
  }

  async function resendLoginOtp(challengeId) {
    return apiRequest("/api/auth/resend-otp", {
      method: "POST",
      body: JSON.stringify({ challenge_id: challengeId }),
    });
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
    verifyLoginOtp,
    resendLoginOtp,
    logout,
    isAuthenticated: Boolean(user),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
