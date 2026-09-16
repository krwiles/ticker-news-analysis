import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./index.css";

const container = document.getElementById("root");
// getElementById returns HTMLElement | null -- needed so createRoot() below typechecks.
if (!container) {
  throw new Error("Missing #root element");
}

createRoot(container).render(<App />);
