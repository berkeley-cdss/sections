import React from "react";
import { createRoot } from "react-dom/client";
// Bootstrap first, so index.css can override it.
import "bootstrap/dist/css/bootstrap.css";
import "./index.css";
import App from "./App";
import nullThrows from "./nullThrows";

createRoot(nullThrows(document.getElementById("root"))).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
