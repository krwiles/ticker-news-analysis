import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./index.css";

const container = document.getElementById("root");
// getElementById's return type is `HTMLElement | null` -- TypeScript
// won't let createRoot() below accept a possibly-null value, so this
// isn't defensive fluff, it's what makes the next line typecheck at all.
if (!container) {
  throw new Error("Missing #root element");
}

createRoot(container).render(<App />);
