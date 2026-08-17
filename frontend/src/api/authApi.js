import { api } from "./client";

export const authApi = {
  async login(email, password) {
    return api.post("/api/auth/login", {
      email,
      password,
    });
  },

  async register(name, email, password) {
    return api.post("/api/auth/register", {
      name,
      email,
      password,
    });
  },

  async me() {
    return api.get("/api/auth/me");
  },
};