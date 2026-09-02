import { AuthProvider, useAuth } from "@/context/auth";
import { Login } from "@/pages/Login";
import { PatientDashboard } from "@/pages/PatientDashboard";
import { ClinicianDashboard } from "@/pages/ClinicianDashboard";
import { Spinner } from "@/components/ui";

function Routes() {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex min-h-full items-center"><Spinner label="Signing you in" /></div>;
  if (!user) return <Login />;
  return user.role === "patient" ? <PatientDashboard /> : <ClinicianDashboard />;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes />
    </AuthProvider>
  );
}
