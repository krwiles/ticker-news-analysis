import { BrowserRouter, Route, Routes } from "react-router";
import { StatusPage } from "./pages/StatusPage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<StatusPage />} />
      </Routes>
    </BrowserRouter>
  );
}
