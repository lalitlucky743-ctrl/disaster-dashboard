import { AuthProvider, useAuth } from "./context/AuthContext";
import AuthPage from "./components/AuthPage";
import DisasterDashboard from "./components/DisasterDashboard";


function AppContent() {

  const {
    user,
    loading,
    logout,
  } = useAuth();


  if (loading) {

    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-white">
        Loading Disaster Intelligence...
      </div>
    );
  }


  if (!user) {

    return <AuthPage />;
  }


  return (
    <div className="min-h-screen">

      <DisasterDashboard
        user={user}
        onLogout={logout}
      />

    </div>
  );
}


export default function App() {

  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}