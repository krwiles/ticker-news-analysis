import { BrowserRouter, Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import { SearchPage } from "./pages/SearchPage";
import { StatusPage } from "./pages/StatusPage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<StatusPage />} />
          <Route path="/search" element={<SearchPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
