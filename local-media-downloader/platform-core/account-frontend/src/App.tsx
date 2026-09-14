import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import AccountLayout from "./components/AccountLayout";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Products from "./pages/Products";
import Billing from "./pages/Billing";
import Profile from "./pages/Profile";
import Security from "./pages/Security";
import Sessions from "./pages/Sessions";
import ConnectedApps from "./pages/ConnectedApps";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <ProtectedRoute>
                <AccountLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/" element={<Overview />} />
            <Route path="/products" element={<Products />} />
            <Route path="/billing" element={<Billing />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/security" element={<Security />} />
            <Route path="/sessions" element={<Sessions />} />
            <Route path="/connected-apps" element={<ConnectedApps />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
