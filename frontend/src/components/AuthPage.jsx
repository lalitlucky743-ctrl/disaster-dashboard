import { useState } from "react";
import { useAuth } from "../context/AuthContext";

export default function AuthPage() {
  const { login, register } = useAuth();

  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function clearMessages() {
    setError("");
    setSuccess("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    clearMessages();
    setSubmitting(true);

    try {
      const normalizedEmail = email.trim().toLowerCase();

      if (mode === "register") {
        await register(name.trim(), normalizedEmail, password);

        setSuccess("Account created successfully. You can now sign in.");
        setMode("login");
        setPassword("");
        setName("");
        return;
      }

      // Email + password login. AuthContext saves the returned JWT.
      await login(normalizedEmail, password);

      // App.jsx should render the dashboard when the user is authenticated.
    } catch (err) {
      setError(
        err?.message || "Authentication failed. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  }

  function toggleMode() {
    setMode((current) =>
      current === "login" ? "register" : "login"
    );
    setPassword("");
    clearMessages();
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-md">
        <header className="mb-8">
          <div className="text-emerald-400 text-sm font-semibold tracking-[0.18em] uppercase">
            Uttarakhand Disaster Intelligence Platform
          </div>

          <h1 className="text-3xl sm:text-4xl font-bold text-white mt-3">
            {mode === "login"
              ? "Welcome back"
              : "Create your account"}
          </h1>

          <p className="text-slate-400 mt-3 leading-relaxed">
            Sign in with your email and password to access your disaster monitoring dashboard.
          </p>
        </header>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-7 shadow-xl">
          <form onSubmit={handleSubmit} className="space-y-5">
            {mode === "register" && (
              <div>
                <label
                  htmlFor="auth-name"
                  className="text-sm text-slate-300"
                >
                  Full name
                </label>

                <input
                  id="auth-name"
                  name="name"
                  type="text"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  required
                  minLength={2}
                  maxLength={100}
                  autoComplete="name"
                  className="mt-2 w-full rounded-xl bg-slate-950 border border-slate-700 px-4 py-3 text-white outline-none focus:border-emerald-500"
                  placeholder="Your name"
                />
              </div>
            )}

            <div>
              <label
                htmlFor="auth-email"
                className="text-sm text-slate-300"
              >
                Email address
              </label>

              <input
                id="auth-email"
                name="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                maxLength={255}
                className="mt-2 w-full rounded-xl bg-slate-950 border border-slate-700 px-4 py-3 text-white outline-none focus:border-emerald-500"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label
                htmlFor="auth-password"
                className="text-sm text-slate-300"
              >
                Password
              </label>

              <input
                id="auth-password"
                name="password"
                type="password"
                autoComplete={
                  mode === "login"
                    ? "current-password"
                    : "new-password"
                }
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={mode === "register" ? 8 : 1}
                maxLength={256}
                className="mt-2 w-full rounded-xl bg-slate-950 border border-slate-700 px-4 py-3 text-white outline-none focus:border-emerald-500"
                placeholder={
                  mode === "register"
                    ? "Minimum 8 characters"
                    : "Enter your password"
                }
              />
            </div>

            {error && (
              <div
                role="alert"
                className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300"
              >
                {error}
              </div>
            )}

            {success && (
              <div
                role="status"
                className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300"
              >
                {success}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed py-3.5 text-slate-950 font-semibold transition"
            >
              {submitting
                ? "Please wait..."
                : mode === "login"
                  ? "Sign in"
                  : "Create account"}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-slate-400">
            {mode === "login"
              ? "Don't have an account?"
              : "Already have an account?"}

            <button
              type="button"
              onClick={toggleMode}
              className="ml-2 text-emerald-400 hover:text-emerald-300 font-semibold"
            >
              {mode === "login" ? "Create one" : "Sign in"}
            </button>
          </div>
        </div>

        <p className="text-center text-xs text-slate-500 mt-5">
          Disaster Intelligence Platform · Secure Operations
        </p>
      </div>
    </div>
  );
}
