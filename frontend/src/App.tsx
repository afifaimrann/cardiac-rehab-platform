import { useState } from "react";
import { AuthProvider, useAuth } from "@/context/auth";
import { AppShell, type NavKey } from "@/components/AppShell";
import { Login } from "@/pages/Login";
import { PatientOverview } from "@/pages/PatientOverview";
import { AskPanel } from "@/components/AskPanel";
import { AppointmentsPage } from "@/pages/Appointments";
import { ClinicianAssistantPage } from "@/pages/ClinicianAssistant";
import { ClinicianDashboard } from "@/pages/ClinicianDashboard";
import { DiaryPage } from "@/pages/Diary";
import { MessagesPage } from "@/pages/Messages";
import { ProfilePage } from "@/pages/Profile";
import { WalkTestPage } from "@/pages/WalkTest";
import { Spinner } from "@/components/exports";

const PATIENT_NAV: NavKey[] = ["overview", "ask", "walk", "appointments", "messages"];
const CLINICIAN_NAV: NavKey[] = ["caseload", "assistant", "diary"];

function Routes() {
  const { user, loading } = useAuth();
  const [tab, setTab] = useState<NavKey>("overview");
  const [clinicianTab, setClinicianTab] = useState<NavKey>("caseload");
  // Set when the clinician asks about a specific patient from the caseload, so
  // the assistant opens on them rather than on whoever is first in the list.
  const [askAbout, setAskAbout] = useState<string | undefined>();

  if (loading) {
    return <div className="flex h-full items-center justify-center"><Spinner label="Signing you in" /></div>;
  }
  if (!user) return <Login />;

  if (user.role === "patient") {
    return (
      <AppShell nav={PATIENT_NAV} active={tab} onNavigate={setTab}>
        {tab === "ask" ? <AskPanel />
          : tab === "walk" ? <WalkTestPage />
          : tab === "appointments" ? <AppointmentsPage />
          : tab === "messages" ? <MessagesPage />
          : tab === "profile" ? <ProfilePage />
          : <PatientOverview onAsk={() => setTab("ask")} onNavigate={setTab} />}
      </AppShell>
    );
  }

  return (
    <AppShell
      nav={CLINICIAN_NAV}
      active={clinicianTab}
      onNavigate={(key) => { if (key !== "assistant") setAskAbout(undefined); setClinicianTab(key); }}
    >
      {clinicianTab === "diary" ? <DiaryPage />
        : clinicianTab === "profile" ? <ProfilePage />
        : clinicianTab === "assistant" ? <ClinicianAssistantPage initialPatientId={askAbout} />
        : (
          <ClinicianDashboard
            onAskAbout={(patientId) => { setAskAbout(patientId); setClinicianTab("assistant"); }}
          />
        )}
    </AppShell>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes />
    </AuthProvider>
  );
}
