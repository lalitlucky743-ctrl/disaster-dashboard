import { api } from "./client";

export const aiApi = {
  ask(question, location = null) {
    return api.post("/api/ai/ask", {
      question,
      location,
    });
  },
};