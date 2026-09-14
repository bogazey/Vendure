import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import AdminLayout from "./components/AdminLayout";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Users from "./pages/Users";
import Products from "./pages/Products";
import ProductDetail from "./pages/ProductDetail";
import Bundles from "./pages/Bundles";
import Revenue from "./pages/Revenue";
import BillingEvents from "./pages/BillingEvents";
import SystemHealth from "./pages/SystemHealth";
import GiftedAccess from "./pages/GiftedAccess";
import AuditLog from "./pages/AuditLog";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <ProtectedRoute>
                <AdminLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/" element={<Overview />} />
            <Route path="/users" element={<Users />} />
            <Route path="/products" element={<Products />} />
            <Route path="/products/:productId" element={<ProductDetail />} />
            <Route path="/bundles" element={<Bundles />} />
            <Route path="/revenue" element={<Revenue />} />
            <Route path="/billing-events" element={<BillingEvents />} />
            <Route path="/system-health" element={<SystemHealth />} />
            <Route path="/gifted-access" element={<GiftedAccess />} />
            <Route path="/audit-log" element={<AuditLog />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
