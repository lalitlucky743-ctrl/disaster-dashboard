import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";

export default function AuthPage() {
  const {
    login,
    register,
    verifyLoginOtp,
    resendLoginOtp,
  } = useAuth();

  const [mode, setMode] = useState("login");
  const [step, setStep] = useState("credentials");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [challenge, setChallenge] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendCountdown, setResendCountdown] = useState(60);

  useEffect(() => {
    if (step !== "otp") return undefined;

    const timer = window.setInterval(() => {
      setResendCountdown((current) => Math.max(0, current - 1));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [step]);

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
        return;
      }

      // The backend verifies the password and sends an OTP challenge.
      // No access token should be saved until OTP verification succeeds.
      const result = await login(normalizedEmail, password);

      if (!result?.challenge_id || result?.otp_required !== true) {
        throw new Error(
          "The server did not start OTP verification. Check that the updated backend is running and email delivery is configured."
        );
      }

      setChallenge(result);
      setPassword("");
      setOtp("");
      setResendCountdown(60);
      setStep("otp");
      setSuccess(result.message || "Verification code sent to your registered email.");
    } catch (err) {
      setError(err?.message || "Authentication failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleVerifyOtp(event) {
    event.preventDefault();
    clearMessages();

    if (!challenge?.challenge_id) {
      setError("Your verification session is missing. Please sign in again.");
      return;
    }

    if (!/^\d{6}$/.test(otp)) {
      setError("Enter the 6-digit code sent to your email.");
      return;
    }

    setSubmitting(true);
    try {
      // AuthContext saves the JWT only after this endpoint succeeds.
      await verifyLoginOtp(challenge.challenge_id, otp);
      // App.jsx observes the authenticated user and renders the dashboard.
    } catch (err) {
      setError(err?.message || "Could not verify the code. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResendOtp() {
    if (!challenge?.challenge_id || resendCountdown > 0 || resending) return;

    clearMessages();
    setResending(true);
    try {
      const result = await resendLoginOtp(challenge.challenge_id);
      setOtp("");
      setResendCountdown(
        Number.isFinite(Number(result?.resend_available_in_seconds))
          ? Number(result.resend_available_in_seconds)
          : 60
      );
      setSuccess(result?.message || "A new verification code has been sent.");
    } catch (err) {
      const message = err?.message || "Unable to resend the verification code.";
      const waitMatch = message.match(/wait\s+(\d+)\s+seconds?/i);
      if (waitMatch) setResendCountdown(Number(waitMatch[1]));
      setError(message);
    } finally {
      setResending(false);
    }
  }

  function backToCredentials() {
    setStep("credentials");
    setChallenge(null);
    setOtp("");
    setPassword("");
    clearMessages();
  }

  function toggleMode() {
    setMode((current) => current === "login" ? "register" : "login");
    setStep("credentials");
    setChallenge(null);
    setOtp("");
    setPassword("");
    clearMessages();
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-md">
        <header className="mb-8">
          <div className="text-emerald-400 text-sm font-semibold tracking-[0.18em] uppercase">
            Disaster Intelligence Platform
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold text-white mt-3">
            {step === "otp"
              ? "Verify your email"
              : mode === "login"
                ? "Welcome back"
                : "Create your account"}
          </h1>
          <p className="text-slate-400 mt-3 leading-relaxed">
            {step === "otp"
              ? "Enter the one-time code sent to your registered email to finish signing in."
              : "Secure access to your disaster monitoring platform."}
          </p>
        </header>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-7 shadow-xl">
          {step === "credentials" ? (
            <form onSubmit={handleSubmit} className="space-y-5">
              {mode === "register" && (
                <div>
                  <label htmlFor="auth-name" className="text-sm text-slate-300">
                    Full name
                  </label>
                  <input
                    id="auth-name"
                    name="name"
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
                <label htmlFor="auth-email" className="text-sm text-slate-300">
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
                <label htmlFor="auth-password" className="text-sm text-slate-300">
                  Password
                </label>
                <input
                  id="auth-password"
                  name="password"
                  type="password"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  minLength={mode === "register" ? 8 : 1}
                  maxLength={256}
                  className="mt-2 w-full rounded-xl bg-slate-950 border border-slate-700 px-4 py-3 text-white outline-none focus:border-emerald-500"
                  placeholder={mode === "register" ? "Minimum 8 characters" : "Enter your password"}
                />
              </div>

              {error && (
                <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                  {error}
                </div>
              )}
              {success && (
                <div role="status" className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
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
                    ? "Continue to email verification"
                    : "Create account"}
              </button>
            </form>
          ) : (
            <form onSubmit={handleVerifyOtp} className="space-y-5">
              <div className="rounded-xl border border-slate-700 bg-slate-950/70 px-4 py-3">
                <p className="text-xs text-slate-400">Verification code sent to</p>
                <p className="mt-1 text-sm font-medium text-slate-100 break-all">
                  {challenge?.email_masked || email}
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  The code expires in {Math.floor((challenge?.expires_in_seconds || 300) / 60)} minutes. Check your Inbox and Spam folder.
                </p>
              </div>

              <div>
                <label htmlFor="auth-otp" className="text-sm text-slate-300">
                  6-digit email OTP
                </label>
                <input
                  id="auth-otp"
                  name="otp"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  value={otp}
                  onChange={(event) => {
                    setOtp(event.target.value.replace(/\D/g, "").slice(0, 6));
                    if (error) setError("");
                  }}
                  required
                  autoFocus
                  className="mt-2 w-full rounded-xl bg-slate-950 border border-slate-700 px-4 py-4 text-center text-2xl tracking-[0.55em] font-semibold text-white outline-none focus:border-emerald-500"
                  placeholder="000000"
                  aria-describedby="auth-otp-help"
                />
                <p id="auth-otp-help" className="mt-2 text-xs text-slate-500">
                  Never share this code with anyone.
                </p>
              </div>

              {error && (
                <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                  {error}
                </div>
              )}
              {success && (
                <div role="status" className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
                  {success}
                </div>
              )}

              <button
                type="submit"
                disabled={submitting || otp.length !== 6}
                className="w-full rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed py-3.5 text-slate-950 font-semibold transition"
              >
                {submitting ? "Verifying code..." : "Verify OTP and sign in"}
              </button>

              <div className="text-center text-sm text-slate-400">
                Didn't receive the email?{" "}
                <button
                  type="button"
                  onClick={handleResendOtp}
                  disabled={resending || resendCountdown > 0}
                  className="font-semibold text-emerald-400 hover:text-emerald-300 disabled:text-slate-500 disabled:cursor-not-allowed"
                >
                  {resending
                    ? "Sending..."
                    : resendCountdown > 0
                      ? `Resend in ${resendCountdown}s`
                      : "Resend code"}
                </button>
              </div>

              <button
                type="button"
                onClick={backToCredentials}
                className="w-full text-sm text-slate-400 hover:text-white py-1"
              >
                Back to sign in
              </button>
            </form>
          )}

          {step === "credentials" && (
            <div className="mt-6 text-center text-sm text-slate-400">
              {mode === "login" ? "Don't have an account?" : "Already have an account?"}
              <button
                type="button"
                onClick={toggleMode}
                className="ml-2 text-emerald-400 hover:text-emerald-300 font-semibold"
              >
                {mode === "login" ? "Create one" : "Sign in"}
              </button>
            </div>
          )}
        </div>

        <p className="text-center text-xs text-slate-500 mt-5">
          Disaster Intelligence Platform · Secure Operations
        </p>
      </div>
    </div>
  );
}
