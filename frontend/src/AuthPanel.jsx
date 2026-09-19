import { useState } from "react";


const API =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";


export default function AuthPanel({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const isRegister = mode === "register";

  function updateField(event) {
    setForm({
      ...form,
      [event.target.name]: event.target.value,
    });
  }

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");

    const endpoint = isRegister
      ? "/auth/register"
      : "/auth/login";

    const body = isRegister
      ? form
      : {
          email: form.email,
          password: form.password,
        };

    try {
      const response = await fetch(API + endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Authentication failed.");
      }

      localStorage.setItem("access_token", data.access_token);
      onAuthenticated(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <p className="eyebrow">CLIMATE INTELLIGENCE</p>
        <h1>{isRegister ? "Create your account" : "Welcome back"}</h1>
        <p className="auth-subtitle">
          Access India heatwave forecasts and decision support.
        </p>

        <form onSubmit={submit}>
          {isRegister && (
            <label>
              Full name
              <input
                name="full_name"
                value={form.full_name}
                onChange={updateField}
                required
              />
            </label>
          )}

          <label>
            Email
            <input
              name="email"
              type="email"
              value={form.email}
              onChange={updateField}
              required
            />
          </label>

          <label>
            Password
            <input
              name="password"
              type="password"
              minLength="8"
              value={form.password}
              onChange={updateField}
              required
            />
          </label>

          {error && <p className="auth-error">{error}</p>}

          <button className="primary-button auth-submit" disabled={loading}>
            {loading
              ? "Please wait..."
              : isRegister
                ? "Register"
                : "Login"}
          </button>
        </form>

        <button
          className="switch-auth"
          onClick={() => {
            setMode(isRegister ? "login" : "register");
            setError("");
          }}
        >
          {isRegister
            ? "Already have an account? Login"
            : "New user? Create an account"}
        </button>
      </section>
    </main>
  );
}
