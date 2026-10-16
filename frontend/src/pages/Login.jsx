import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Eye,
  EyeOff,
  LockKeyhole,
  Mail,
  Radio,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

import { useAuth } from "../context/AuthContext";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, verifyLoginOtp, resendLoginOtp } = useAuth();

  const [form, setForm] = useState({ email: "", password: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState("");
  const [step, setStep] = useState("credentials");
  const [challenge, setChallenge] = useState(null);
  const [otp, setOtp] = useState("");
  const [resendCountdown, setResendCountdown] = useState(60);

  useEffect(() => {
    if (step !== "otp" || resendCountdown <= 0) return undefined;
    const timer = window.setInterval(() => {
      setResendCountdown((current) => Math.max(0, current - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [step, resendCountdown]);

  const destination = location.state?.from?.pathname || "/";

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((previous) => ({ ...previous, [name]: value }));
    if (error) setError("");
  };

  const handlePasswordSubmit = async (event) => {
    event.preventDefault();
    if (!form.email.trim() || !form.password) {
      setError("Please enter your email and password.");
      return;
    }

    try {
      setSubmitting(true);
      setError("");
      const result = await login(form.email.trim(), form.password);
      setChallenge(result);
      setOtp("");
      setResendCountdown(60);
      setStep("otp");
    } catch (err) {
      setError(
        err.message === "SESSION_EXPIRED"
          ? "Your session has expired. Please sign in again."
          : err.message || "Unable to sign in."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleOtpSubmit = async (event) => {
    event.preventDefault();
    if (!challenge?.challenge_id) {
      setError("Your verification session is missing. Please sign in again.");
      return;
    }
    if (!/^\d{6}$/.test(otp)) {
      setError("Enter the 6-digit code sent to your email.");
      return;
    }

    try {
      setSubmitting(true);
      setError("");
      await verifyLoginOtp(challenge.challenge_id, otp);
      navigate(destination, { replace: true });
    } catch (err) {
      setError(
        err.message === "SESSION_EXPIRED"
          ? "Your session has expired. Please sign in again."
          : err.message || "Unable to verify the code."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleResendOtp = async () => {
    if (!challenge?.challenge_id || resendCountdown > 0 || resending) return;
    try {
      setResending(true);
      setError("");
      const result = await resendLoginOtp(challenge.challenge_id);
      setResendCountdown(result.resend_available_in_seconds || 60);
      setOtp("");
      setChallenge((previous) => ({ ...previous, ...result }));
    } catch (err) {
      setError(err.message || "Unable to resend the verification code.");
    } finally {
      setResending(false);
    }
  };

  const returnToPassword = () => {
    setStep("credentials");
    setChallenge(null);
    setOtp("");
    setError("");
    setResendCountdown(60);
  };

  return (
    <div className="min-h-screen bg-[#0b1017] text-slate-100 flex items-center justify-center p-4 relative overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_15%_15%,rgba(51,111,148,0.14),transparent_38%),radial-gradient(circle_at_85%_85%,rgba(50,120,98,0.09),transparent_36%)]" />

      <div className="relative w-full max-w-[430px]">
        <div className="text-center mb-7">
          <div className="mx-auto mb-4 w-12 h-12 rounded-xl border border-sky-500/25 bg-sky-500/10 flex items-center justify-center">
            <Radio className="w-6 h-6 text-sky-400" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">Disaster Intelligence</h1>
          <p className="mt-2 text-sm text-slate-400">Secure command &amp; intelligence platform</p>
        </div>

        <div className="rounded-2xl border border-slate-700/80 bg-[#151c25]/95 shadow-2xl p-6 sm:p-7">
          {step === "credentials" ? (
            <>
              <div className="mb-6">
                <h2 className="text-lg font-semibold">Sign in</h2>
                <p className="text-xs text-slate-400 mt-1">Access your disaster intelligence workspace.</p>
              </div>

              {error && <ErrorMessage message={error} />}

              <form onSubmit={handlePasswordSubmit} className="space-y-4">
                <div>
                  <label htmlFor="email" className="block text-xs font-medium text-slate-300 mb-2">Email address</label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input
                      id="email"
                      name="email"
                      type="email"
                      autoComplete="email"
                      required
                      value={form.email}
                      onChange={handleChange}
                      placeholder="you@example.com"
                      className="w-full h-11 rounded-xl border border-slate-700 bg-[#0e141c] pl-10 pr-3 text-sm text-slate-100 placeholder:text-slate-500 outline-none focus:border-sky-500/70 focus:ring-2 focus:ring-sky-500/10 transition"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="password" className="block text-xs font-medium text-slate-300 mb-2">Password</label>
                  <div className="relative">
                    <LockKeyhole className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input
                      id="password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      autoComplete="current-password"
                      required
                      value={form.password}
                      onChange={handleChange}
                      placeholder="Enter your password"
                      className="w-full h-11 rounded-xl border border-slate-700 bg-[#0e141c] pl-10 pr-11 text-sm text-slate-100 placeholder:text-slate-500 outline-none focus:border-sky-500/70 focus:ring-2 focus:ring-sky-500/10 transition"
                    />
                    <button type="button" aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword((value) => !value)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-200">
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <button type="submit" disabled={submitting} className="w-full h-11 mt-2 rounded-xl bg-sky-700 hover:bg-sky-600 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold transition flex items-center justify-center gap-2">
                  {submitting ? <><Spinner /> Checking credentials...</> : <>Continue <ArrowRight className="w-4 h-4" /></>}
                </button>
              </form>

              <div className="flex items-center gap-3 my-6">
                <div className="h-px bg-slate-700 flex-1" />
                <span className="text-[10px] uppercase tracking-widest text-slate-500">Two-step verification</span>
                <div className="h-px bg-slate-700 flex-1" />
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <ShieldCheck className="w-4 h-4 text-emerald-400" /> Password and email code are required
              </div>
              <p className="text-center text-xs text-slate-400 mt-6">
                Don't have an account? <Link to="/register" className="text-sky-400 hover:text-sky-300 font-medium">Create account</Link>
              </p>
            </>
          ) : (
            <>
              <button type="button" onClick={returnToPassword} className="inline-flex items-center gap-2 text-xs text-slate-400 hover:text-slate-100 mb-5">
                <ArrowLeft className="w-4 h-4" /> Back to sign in
              </button>
              <div className="w-11 h-11 rounded-xl border border-sky-500/25 bg-sky-500/10 flex items-center justify-center mb-4">
                <Mail className="w-5 h-5 text-sky-400" />
              </div>
              <h2 className="text-lg font-semibold">Verify your email</h2>
              <p className="text-xs text-slate-400 mt-2 leading-relaxed">
                Enter the 6-digit code sent to <span className="font-medium text-slate-200">{challenge?.email_masked || "your registered email"}</span>. The code expires in 5 minutes.
              </p>

              {error && <div className="mt-5"><ErrorMessage message={error} /></div>}

              <form onSubmit={handleOtpSubmit} className="space-y-4 mt-5">
                <div>
                  <label htmlFor="login-otp" className="block text-xs font-medium text-slate-300 mb-2">6-digit verification code</label>
                  <input
                    id="login-otp"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    required
                    value={otp}
                    onChange={(event) => {
                      setOtp(event.target.value.replace(/\D/g, "").slice(0, 6));
                      if (error) setError("");
                    }}
                    placeholder="000000"
                    aria-describedby="otp-help"
                    className="w-full h-14 rounded-xl border border-slate-700 bg-[#0e141c] px-4 text-center text-xl font-semibold tracking-[0.55em] text-slate-100 placeholder:text-slate-600 outline-none focus:border-sky-500/70 focus:ring-2 focus:ring-sky-500/10 transition"
                  />
                  <p id="otp-help" className="text-[11px] text-slate-500 mt-2">Never share this code with anyone.</p>
                </div>
                <button type="submit" disabled={submitting || otp.length !== 6} className="w-full h-11 rounded-xl bg-sky-700 hover:bg-sky-600 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold transition flex items-center justify-center gap-2">
                  {submitting ? <><Spinner /> Verifying code...</> : <>Verify and sign in <ArrowRight className="w-4 h-4" /></>}
                </button>
              </form>

              <div className="mt-5 text-center text-xs text-slate-400">
                Didn't receive the email?{" "}
                <button type="button" onClick={handleResendOtp} disabled={resending || resendCountdown > 0} className="inline-flex items-center gap-1 text-sky-400 hover:text-sky-300 disabled:text-slate-500 disabled:cursor-not-allowed font-medium">
                  {resending ? <><Spinner /> Sending...</> : <><RefreshCw className="w-3 h-3" /> {resendCountdown > 0 ? `Resend in ${resendCountdown}s` : "Resend code"}</>}
                </button>
              </div>
            </>
          )}
        </div>

        <p className="text-center text-[10px] text-slate-500 mt-5">Disaster Intelligence Platform • Secure Operations</p>
      </div>
    </div>
  );
}

function ErrorMessage({ message }) {
  return (
    <div className="mb-5 flex gap-3 rounded-xl border border-red-500/25 bg-red-500/10 p-3" role="alert">
      <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
      <p className="text-xs text-red-200">{message}</p>
    </div>
  );
}

function Spinner() {
  return <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" aria-hidden="true" />;
}
