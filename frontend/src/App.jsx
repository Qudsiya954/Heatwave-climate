import { useEffect, useState } from "react";
import {
  CircleMarker,
  MapContainer,
  Popup,
  TileLayer,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";
import "./App.css";

const API =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

function color(level) {
  return {
    Critical: "#991b1b",
    High: "#dc2626",
    Moderate: "#f59e0b",
    Low: "#16a34a",
  }[level] || "#64748b";
}

function value(number, digits = 1) {
  if (number === null || number === undefined) {
    return "-";
  }

  return Number(number).toFixed(digits);
}

export default function App() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [advisories, setAdvisories] = useState([]);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/risk?limit=400`).then((r) => r.json()),
      fetch(`${API}/advisory?limit=1`).then((r) => r.json()),
    ])
      .then(([riskData, advisoryData]) => {
        setRows(riskData);
        setAdvisories(advisoryData);
      })
      .catch((err) => setError(err.message));
  }, []);
  if (error) {
    return <main className="error">{error}</main>;
  }

  if (!rows.length) {
    return <main className="loading">Loading climate intelligence...</main>;
  }

  const top = rows[0];
  const decision = top.decision || "No Warning";

  const hotspots = rows
    .filter((row) => row.hotspot)
    .sort(
      (a, b) =>
        Number(b.hotspot_score)
        - Number(a.hotspot_score)
    )
    .slice(0, 10);
  const currentAdvisory =
    advisories[0]?.advisory || top.advisory;

  return (
    <main className="dashboard">
      <header>
        <p className="eyebrow">CLIMATE INTELLIGENCE</p>
        <h1>India Heatwave Risk Dashboard</h1>
        <p>
          Forecast, hotspot, AWS, DHRI, and decision-support
          intelligence.
        </p>
      </header>

      <section className="cards">
        <div className="card">
          <span>Predicted Tmax</span>
          <strong>{value(top.predicted_temperature)}°C</strong>
        </div>

        <div className="card">
          <span>Heatwave Probability</span>
          <strong>
            {value(top.heatwave_probability * 100)}%
          </strong>
        </div>

        <div className="card">
          <span>DHRI</span>
          <strong>{value(top.dhri)}</strong>
        </div>

        <div className="card">
          <span>Decision</span>
          <strong>{decision}</strong>
        </div>
      </section>

      <section className="grid">
        <div className="panel map-panel">
          <h2>India Risk Map</h2>

          <MapContainer
            center={[22.5, 79]}
            zoom={5}
            scrollWheelZoom={true}
          >
            <TileLayer
              attribution="&copy; OpenStreetMap contributors"
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            {rows.map((row) => (
              <CircleMarker
                key={`${row.latitude}-${row.longitude}`}
                center={[
                  Number(row.latitude),
                  Number(row.longitude),
                ]}
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
                  DHRI: {value(row.dhri)}
                  <br />
                  Severity: {row.severity}
                  <br />
                  Decision: {row.decision}
                </Popup>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>

        <div className="panel">
          <h2>Top Historical Hotspots</h2>

          {hotspots.map((row) => (
            <div
              className="hotspot"
              key={`${row.latitude}-${row.longitude}`}
            >
              <span>
                {row.latitude}, {row.longitude}
              </span>
              <strong>
                {value(row.hotspot_score)}
              </strong>
            </div>
          ))}

          {!hotspots.length && (
            <p>No hotspot locations found.</p>
          )}
        </div>
      </section>

      <section className="panel advisory">
        <h2>Decision Support</h2>
        <p>
          <b>{top.decision}</b>
        </p>
        <p>
          {currentAdvisory ||
            "No advisory stored for this location yet."}
        </p>
      </section>
    </main>
  );
}