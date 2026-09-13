import { BrowserRouter, Route, Routes } from "react-router";
import { SearchPage } from "./pages/SearchPage";
import { StatusPage } from "./pages/StatusPage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<StatusPage />} />
        {/* Added in lesson 11, same pattern as the route above -- no new
            React Router concepts used here on purpose. Lesson 13 is where
            routing itself becomes the actual subject, including this route. */}
        <Route path="/search" element={<SearchPage />} />
      </Routes>
    </BrowserRouter>
  );
}
