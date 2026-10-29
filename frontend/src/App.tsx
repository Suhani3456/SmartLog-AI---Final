import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import DashboardPage from "./pages/Dashboard";
import LivePage from "./pages/Live";
import ClassifyPage from "./pages/Classify";
import IncidentsPage from "./pages/Incidents";
import AnomaliesPage from "./pages/Anomalies";
import ModelPage from "./pages/Model";
import UploadPage from "./pages/Upload";
import AboutPage from "./pages/About";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/live" element={<LivePage />} />
          <Route path="/classify" element={<ClassifyPage />} />
          <Route path="/incidents" element={<IncidentsPage />} />
          <Route path="/anomalies" element={<AnomaliesPage />} />
          <Route path="/model" element={<ModelPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/about" element={<AboutPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
