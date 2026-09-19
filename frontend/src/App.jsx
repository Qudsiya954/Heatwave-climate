import { useEffect, useState } from "react";
import {
  CircleMarker,
  MapContainer,
  Popup,
  TileLayer,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";
import "./App.css";
import AuthPanel from "./AuthPanel";

const API = (
  import.meta.env.VITE_API_URL ||
  "https://climate-intelligence-api.onrender.com"
).replace(/\/+$/, "");

const riskLevels = ["Low", "Moderate", "High", "Critical"];
const severityLevels = ["Normal", "Moderate", "High", "Extreme"];
const stakeholders = [
  "Citizen",
  "Farmer",
  "Health Agency",
  "Local Authority",
];

function color(level) {
  return {
    Critical: "#991b1b",
    High: "#dc2626",
    Moderate: "#f59e0b",
    Low: "#16a34a",
  }[level] || "#64748b";
}

function badgeClass(value = "") {
  return value.toLowerCase().replace(/\s+/g, "-");
}

function value(number, digits = 1) {
  if (number === null || number === undefined) {
    return "-";
  }

  return Number(number).toFixed(digits);
}

async function getJson(url, signal, token) {
  const response = await fetch(url, {
    signal,
    headers: token
      ? { Authorization: "Bearer " + token }
      : {},
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("Your session expired. Please log in again.");
    }

    throw new Error("Request failed: " + response.status);
  }

  return response.json();
}

export default function App() {
  const [rows, setRows] = useState([]);
  const [advisories, setAdvisories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [riskFilter, setRiskFilter] = useState("All");
  const [severityFilter, setSeverityFilter] = useState("All");
  const [activeStakeholder, setActiveStakeholder] = useState("Citizen");
  const [token, setToken] = useState(() =>
    localStorage.getItem("access_token"),
  );
  const [user, setUser] = useState(null);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }

    const controller = new AbortController();

    setLoading(true);
    setError("");

    Promise.all([
      getJson(API + "/risk?limit=400", controller.signal, token),
      getJson(API + "/advisory?limit=50", controller.signal, token),
    ])
      .then(([riskData, advisoryData]) => {
        setRows(Array.isArray(riskData) ? riskData : []);
        setAdvisories(Array.isArray(advisoryData) ? advisoryData : []);
      })
      .catch((err) => {
        if (err.name !== "AbortError") {
          setError(err.message || "Unable to load dashboard data.");
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [reloadKey, token]);

  function logout() {
    localStorage.removeItem("access_token");
    setToken("");
    setUser(null);
    setRows([]);
    setAdvisories([]);
  }

  if (!token) {
    return (
      <AuthPanel
        onAuthenticated={(data) => {
          setToken(data.access_token);
          setUser(data.user);
        }}
      />
    );
  }

  if (loading) {
    return (
      <main className="status-page">
        <div className="status-card">
          <div className="spinner" />
          <h2>Loading climate intelligence</h2>
          <p>Fetching forecasts, hotspots, and advisories...</p>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="status-page">
        <div className="status-card error-card">
          <h2>Dashboard unavailable</h2>
          <p>{error}</p>
          <button
            className="primary-button"
            onClick={() => setReloadKey((key) => key + 1)}
          >
            Try again
          </button>
          <button className="switch-auth" onClick={logout}>
            Log out
          </button>
        </div>
      </main>
    );
  }

  if (!rows.length) {
    return (
      <main className="status-page">
        <div className="status-card">
          <h2>No intelligence data found</h2>
          <p>Run the prediction pipeline and refresh this dashboard.</p>
        </div>
      </main>
    );
  }

  const visibleRows = rows.filter((row) => {
    const matchesRisk =
      riskFilter === "All" || row.risk_level === riskFilter;
    const matchesSeverity =
      severityFilter === "All" || row.severity === severityFilter;

    return matchesRisk && matchesSeverity;
  });

  const top = visibleRows[0] || rows[0];
  const decision = top.decision || "No Warning";
  const riskLevel = top.risk_level || "Low";
  const severity = top.severity || "Normal";
  const advisory = advisories.find(
    (item) => item.stakeholder === activeStakeholder,
  );
  const currentAdvisory = advisory?.advisory || top.advisory;

  const hotspots = rows
    .filter((row) => row.hotspot)
    .sort(
      (a, b) =>
        Number(b.hotspot_score) - Number(a.hotspot_score),
    )
    .slice(0, 10);

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <p className="eyebrow">CLIMATE INTELLIGENCE</p>
        <h1>India Heatwave Risk Dashboard</h1>
        <p className="subtitle">
          Forecast, hotspot, AWS, DHRI, and decision-support intelligence.
        </p>
        <p className="forecast-date">
          Forecast date: <strong>{top.forecast_date || "Unavailable"}</strong>
        </p>
        <div className="user-bar">
          <span>
            Signed in{user?.full_name ? " as " + user.full_name : ""}
          </span>
          <button className="logout-button" onClick={logout}>
            Log out
          </button>
        </div>
      </header>

      <section className="cards">
        <div className="card">
          <span>Predicted Tmax</span>
          <strong>{value(top.predicted_temperature)}°C</strong>
        </div>

        <div className="card">
          <span>Heatwave Probability</span>
          <strong>{value(top.heatwave_probability * 100)}%</strong>
        </div>

        <div className="card">
          <span>DHRI</span>
          <strong>{value(top.dhri)}</strong>
        </div>

        <div className="card">
          <span>Severity</span>
          <strong className={"badge " + badgeClass(severity)}>
            {severity}
          </strong>
        </div>

        <div className="card decision-card">
          <span>Decision</span>
          <strong>{decision}</strong>
          <span className={"badge " + badgeClass(riskLevel)}>
            {riskLevel} Risk
          </span>
        </div>
      </section>

      <section className="grid">
        <div className="panel map-panel">
          <div className="panel-heading">
            <div>
              <h2>India Risk Map</h2>
              <p className="muted">
                Showing {visibleRows.length} of {rows.length} grid cells
              </p>
            </div>

            <div className="filters">
              <label>
                Risk
                <select
                  value={riskFilter}
                  onChange={(event) => setRiskFilter(event.target.value)}
                >
                  <option>All</option>
                  {riskLevels.map((level) => (
                    <option key={level}>{level}</option>
                  ))}
                </select>
              </label>

              <label>
                Severity
                <select
                  value={severityFilter}
                  onChange={(event) =>
                    setSeverityFilter(event.target.value)
                  }
                >
                  <option>All</option>
                  {severityLevels.map((level) => (
                    <option key={level}>{level}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          <MapContainer
            center={[22.5, 79]}
            zoom={5}
            scrollWheelZoom={true}
          >
            <TileLayer
              attribution="&copy; OpenStreetMap contributors"
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            {visibleRows.map((row) => (
              <CircleMarker
                key={row.latitude + "-" + row.longitude}
                center={[Number(row.latitude), Number(row.longitude)]}
                radius={6}
                pathOptions={{
                  color: color(row.risk_level),
                  fillColor: color(row.risk_level),
                  fillOpacity: 0.75,
                }}
              >
                <Popup>
                  <b>
                    {row.latitude}, {row.longitude}
                  </b>
                  <br />
                  Tmax: {value(row.predicted_temperature)}°C
                  <br />
                  Heatwave probability: {value(row.heatwave_probability * 100)}%
                  <br />
                  DHRI: {value(row.dhri)}
                  <br />
                  Risk: {row.risk_level}
                  <br />
                  Severity: {row.severity}
                  <br />
                  Decision: {row.decision || "No Warning"}
                </Popup>
              </CircleMarker>
            ))}
          </MapContainer>

          {!visibleRows.length && (
            <p className="empty-message">No locations match these filters.</p>
          )}

          <div className="legend">
            <strong>Risk level</strong>
            {riskLevels.map((level) => (
              <span key={level}>
                <i style={{ backgroundColor: color(level) }} />
                {level}
              </span>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-heading">
            <div>
              <h2>Top Historical Hotspots</h2>
              <p className="muted">Historical hotspot score</p>
            </div>
            <span className="count-badge">{hotspots.length}</span>
          </div>

          {hotspots.map((row) => (
            <div
              className="hotspot"
              key={row.latitude + "-" + row.longitude}
            >
              <span>
                {row.latitude}, {row.longitude}
              </span>
              <strong>{value(row.hotspot_score)}</strong>
            </div>
          ))}

          {!hotspots.length && (
            <p className="empty-message">No hotspot locations found.</p>
          )}
        </div>
      </section>

      <section className="panel advisory">
        <div className="panel-heading">
          <div>
            <h2>Decision Support</h2>
            <p className="muted">
              Actionable intelligence for the selected forecast
            </p>
          </div>
          <span className={"badge " + badgeClass(riskLevel)}>
            {riskLevel} Risk
          </span>
        </div>

        <div className="decision-summary">
          <div>
            <span>Decision</span>
            <strong>{decision}</strong>
          </div>
          <div>
            <span>Severity</span>
            <strong>{severity}</strong>
          </div>
          <div>
            <span>Location</span>
            <strong>
              {top.latitude}, {top.longitude}
            </strong>
          </div>
        </div>

        <div className="stakeholder-tabs" role="tablist">
          {stakeholders.map((stakeholder) => (
            <button
              key={stakeholder}
              className={activeStakeholder === stakeholder ? "active" : ""}
              onClick={() => setActiveStakeholder(stakeholder)}
            >
              {stakeholder}
            </button>
          ))}
        </div>

        <div className="advisory-content">
          <h3>{activeStakeholder} Advisory</h3>
          <p>
            {currentAdvisory ||
              "No " +
                activeStakeholder.toLowerCase() +
                " advisory is stored for this forecast yet."}
          </p>
        </div>
      </section>
    </main>
  );
}
