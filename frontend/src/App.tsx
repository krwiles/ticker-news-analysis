import { BrowserRouter, Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import { SearchPage } from "./pages/SearchPage";
import { StatusPage } from "./pages/StatusPage";

// The whole app's route table -- two real pages, both wrapped in one
// shared Layout (nav + <Outlet />, see Layout.tsx) so navigating between
// them doesn't trigger a full page reload. Client-side routing only:
// BrowserRouter uses the real browser History API, not a hash fragment.
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
