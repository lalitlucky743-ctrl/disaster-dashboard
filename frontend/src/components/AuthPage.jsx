import { useState } from "react";
import { useAuth } from "../context/AuthContext";


export default function AuthPage() {

  const {
    login,
    register,
  } = useAuth();


  const [
    mode,
    setMode
  ] = useState("login");


  const [
    name,
    setName
  ] = useState("");


  const [
    email,
    setEmail
  ] = useState("");


  const [
    password,
    setPassword
  ] = useState("");


  const [
    error,
    setError
  ] = useState("");


  const [
    success,
    setSuccess
  ] = useState("");


  const [
    submitting,
    setSubmitting
  ] = useState(false);


  async function handleSubmit(e) {

    e.preventDefault();

    setError("");
    setSuccess("");
    setSubmitting(true);


    try {

      if (mode === "register") {

        await register(
          name,
          email,
          password
        );


        setSuccess(
          "Account created successfully. You can now sign in."
        );


        setMode("login");

        setPassword("");

      } else {

        await login(
          email,
          password
        );

      }

    } catch (err) {

      setError(
        err.message ||
        "Authentication failed"
      );

    } finally {

      setSubmitting(false);
    }
  }


  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center px-6">

      <div className="w-full max-w-md">

        <div className="mb-8">

          <div className="text-emerald-400 text-sm font-semibold tracking-widest uppercase">
            Disaster Intelligence
          </div>

          <h1 className="text-4xl font-bold text-white mt-3">
            {mode === "login"
              ? "Welcome back"
              : "Create your account"}
          </h1>

          <p className="text-slate-400 mt-3">
            Secure access to your disaster monitoring platform.
          </p>

        </div>


        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-7 shadow-2xl">

          <form
            onSubmit={handleSubmit}
            className="space-y-5"
          >

            {mode === "register" && (

              <div>

                <label className="text-sm text-slate-300">
                  Full name
                </label>

                <input
                  value={name}
                  onChange={(e) =>
                    setName(e.target.value)
                  }
                  required
                  minLength={2}
                  className="mt-2 w-full rounded-xl bg-slate-950 border border-slate-700 px-4 py-3 text-white outline-none focus:border-emerald-500"
                  placeholder="Your name"
                />

              </div>
            )}


            <div>

              <label className="text-sm text-slate-300">
                Email
              </label>

              <input
                type="email"
                value={email}
                onChange={(e) =>
                  setEmail(e.target.value)
                }
                required
                className="mt-2 w-full rounded-xl bg-slate-950 border border-slate-700 px-4 py-3 text-white outline-none focus:border-emerald-500"
                placeholder="you@example.com"
              />

            </div>


            <div>

              <label className="text-sm text-slate-300">
                Password
              </label>

              <input
                type="password"
                value={password}
                onChange={(e) =>
                  setPassword(e.target.value)
                }
                required
                minLength={8}
                className="mt-2 w-full rounded-xl bg-slate-950 border border-slate-700 px-4 py-3 text-white outline-none focus:border-emerald-500"
                placeholder="Minimum 8 characters"
              />

            </div>


            {error && (

              <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                {error}
              </div>

            )}


            {success && (

              <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
                {success}
              </div>

            )}


            <button
              disabled={submitting}
              className="w-full rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 py-3.5 text-slate-950 font-semibold transition"
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
              onClick={() => {
                setMode(
                  mode === "login"
                    ? "register"
                    : "login"
                );

                setError("");
                setSuccess("");
              }}
              className="ml-2 text-emerald-400 hover:text-emerald-300 font-semibold"
            >
              {mode === "login"
                ? "Create one"
                : "Sign in"}
            </button>

          </div>

        </div>

      </div>

    </div>
  );
}