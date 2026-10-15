import AppRoutes from "./routes/appRoutes";
import ScrollToTop from "./routes/ScrollToTop";
import PublicSiteShell from "./components/PublicSiteShell";

import "./App.css";

function App() {
  return (
    <PublicSiteShell>
      <ScrollToTop />
      <AppRoutes />
    </PublicSiteShell>
  );
}

export default App;
