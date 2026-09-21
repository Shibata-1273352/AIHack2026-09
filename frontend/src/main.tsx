import React from "react";
import ReactDOM from "react-dom/client";
import "./theme.css";
import ConsolePage from "./ConsolePage";
import ApprovePage from "./ApprovePage";
import OpsPage from "./OpsPage";

function App() {
  const path = window.location.pathname;
  // /approve は実 iPad で開くためレスポンシブのまま（Stage でラップしない）
  if (path.startsWith("/approve")) return <ApprovePage />;
  if (path.startsWith("/ops")) return <OpsPage />;
  return <ConsolePage />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
