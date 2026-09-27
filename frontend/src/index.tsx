import { createRoot } from "react-dom/client";
import { App } from "./App";
import { getInitialTheme, setTheme } from "./theme";
import "./index.css";

// Applied before the first render -- otherwise the page would flash the wrong theme for a frame.
setTheme(getInitialTheme());

const container = document.getElementById("root");
// getElementById returns HTMLElement | null -- needed so createRoot() below typechecks.
if (!container) {
  throw new Error("Missing #root element");
}

createRoot(container).render(<App />);
