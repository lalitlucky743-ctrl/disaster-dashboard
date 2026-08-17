import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  ArrowRight,
  Eye,
  EyeOff,
  LockKeyhole,
  Mail,
  Radio,
  ShieldCheck,
} from "lucide-react";

import { useAuth } from "../context/AuthContext";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();

  const { login } = useAuth();

  const [form, setForm] = useState({
    email: "",
    password: "",
  });

  const [showPassword, setShowPassword] =
    useState(false);

  const [submitting, setSubmitting] =
    useState(false);

  const [error, setError] = useState("");

  const handleChange = (event) => {
    const { name, value } = event.target;

    setForm((previous) => ({
      ...previous,
      [name]: value,
    }));

    if (error) {
      setError("");
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!form.email || !form.password) {
      setError("Please enter your email and password.");
      return;
    }

    try {
      setSubmitting(true);
      setError("");

      await login(
        form.email.trim(),
        form.password
      );

      const destination =
        location.state?.from?.pathname || "/";

      navigate(destination, {
        replace: true,
      });
    } catch (err) {
      setError(
        err.message === "SESSION_EXPIRED"
          ? "Your session has expired."
          : err.message || "Unable to sign in."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#070B12] text-slate-100 flex items-center justify-center p-4 relative overflow-hidden">

      <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(79,70,229,0.12),transparent_35%),radial-gradient(circle_at_80%_80%,rgba(14,165,233,0.08),transparent_35%)]" />

      <div className="relative w-full max-w-[430px]">

        {/* Brand */}
        <div className="text-center mb-7">
          <div className="mx-auto mb-4 w-12 h-12 rounded-xl border border-indigo-500/30 bg-indigo-500/10 flex items-center justify-center">
            <Radio className="w-6 h-6 text-indigo-400" />
          </div>

          <h1 className="text-2xl font-bold tracking-tight">
            Disaster Intelligence
          </h1>

          <p className="mt-2 text-sm text-slate-500">
            Secure command & intelligence platform
          </p>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-slate-800 bg-[#0D131F]/95 backdrop-blur-xl shadow-2xl p-6">

          <div className="mb-6">
            <h2 className="text-lg font-semibold">
              Sign in
            </h2>

            <p className="text-xs text-slate-500 mt-1">
              Access your disaster intelligence workspace.
            </p>
          </div>

          {error && (
            <div className="mb-5 flex gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-3">
              <AlertCircle className="w-4 h-4 text-red-400 mt-0.5" />

              <p className="text-xs text-red-300">
                {error}
              </p>
            </div>
          )}

          <form
            onSubmit={handleSubmit}
            className="space-y-4"
          >
            {/* Email */}
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-2">
                Email address
              </label>

              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600" />

                <input
                  name="email"
                  type="email"
                  autoComplete="email"
                  value={form.email}
                  onChange={handleChange}
                  placeholder="you@example.com"
                  className="w-full h-11 rounded-xl border border-slate-800 bg-[#080C14] pl-10 pr-3 text-sm text-slate-200 placeholder:text-slate-700 outline-none focus:border-indigo-500/60 focus:ring-2 focus:ring-indigo-500/10 transition"
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-2">
                Password
              </label>

              <div className="relative">
                <LockKeyhole className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600" />

                <input
                  name="password"
                  type={
                    showPassword
                      ? "text"
                      : "password"
                  }
                  autoComplete="current-password"
                  value={form.password}
                  onChange={handleChange}
                  placeholder="Enter your password"
                  className="w-full h-11 rounded-xl border border-slate-800 bg-[#080C14] pl-10 pr-11 text-sm text-slate-200 placeholder:text-slate-700 outline-none focus:border-indigo-500/60 focus:ring-2 focus:ring-indigo-500/10 transition"
                />

                <button
                  type="button"
                  onClick={() =>
                    setShowPassword((value) => !value)
                  }
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-300"
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full h-11 mt-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold transition flex items-center justify-center gap-2"
            >
              {submitting ? (
                <>
                  <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                  Authenticating...
                </>
              ) : (
                <>
                  Sign in
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          <div className="flex items-center gap-3 my-6">
            <div className="h-px bg-slate-800 flex-1" />
            <span className="text-[10px] uppercase tracking-widest text-slate-600">
              Secure access
            </span>
            <div className="h-px bg-slate-800 flex-1" />
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-500">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            JWT protected session
          </div>

          <p className="text-center text-xs text-slate-500 mt-6">
            Don't have an account?{" "}
            <Link
              to="/register"
              className="text-indigo-400 hover:text-indigo-300 font-medium"
            >
              Create account
            </Link>
          </p>
        </div>

        <p className="text-center text-[10px] text-slate-700 mt-5">
          Disaster Intelligence Platform • Secure Operations
        </p>
      </div>
    </div>
  );
}