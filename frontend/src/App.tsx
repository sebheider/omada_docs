import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import { SiteProvider } from './context/SiteContext';
import { Layout } from './components/Layout';
import { ErrorBox, Spinner } from './components/ui';
import { LoginPage, SetupPage } from './pages/Auth';
import { DashboardPage } from './pages/Dashboard';
import { TopologyPage } from './pages/Topology';
import { DeviceDetailPage, DevicesPage } from './pages/Devices';
import { PortDetailPage, PortProfileDetailPage, SwitchesPage } from './pages/Switches';
import { NetworkDetailPage, NetworksPage, RouteDetailPage, VpnDetailPage, WanDetailPage } from './pages/Networks';
import { WlanDetailPage, WlansPage } from './pages/Wlans';
import { AclPage, AclRuleDetailPage, IpGroupDetailPage } from './pages/Acl';
import { NatDetailPage, NatPage } from './pages/Nat';
import { ClientDetailPage, ClientsPage } from './pages/Clients';
import { DocumentEditPage, DocumentationPage, DocumentViewPage } from './pages/Documentation';
import { SearchPage } from './pages/Search';
import { ChangesPage } from './pages/Changes';
import { BackupImportDetailPage, SyncDetailPage, SyncPage } from './pages/Sync';
import { SettingsPage } from './pages/Settings';
import { ExportPage } from './pages/Export';
import { QualityPage } from './pages/Quality';
import { ControllerPage, SiteDetailPage } from './pages/Sites';
import { NotFoundPage } from './pages/NotFound';

export function App() {
  const { state, loading, error, user } = useAuth();
  if (loading) return <Spinner className="h-screen" />;
  if (error && !state)
    return (
      <div className="mx-auto mt-24 max-w-lg p-4">
        <ErrorBox error={error} title="The application backend is not reachable" />
      </div>
    );
  if (state?.setup_required) return <SetupPage />;
  if (!user) return <LoginPage />;

  return (
    <SiteProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="topology" element={<TopologyPage />} />
          <Route path="quality" element={<QualityPage />} />
          <Route path="devices" element={<DevicesPage />} />
          <Route path="devices/:key" element={<DeviceDetailPage />} />
          <Route path="switches" element={<SwitchesPage />} />
          <Route path="switches/profiles/:key" element={<PortProfileDetailPage />} />
          <Route path="switches/:key" element={<DeviceDetailPage section="switches" />} />
          <Route path="ports/:key" element={<PortDetailPage />} />
          <Route path="networks" element={<NetworksPage />} />
          <Route path="networks/wan/:key" element={<WanDetailPage />} />
          <Route path="networks/routes/:key" element={<RouteDetailPage />} />
          <Route path="networks/vpn/:key" element={<VpnDetailPage />} />
          <Route path="networks/:key" element={<NetworkDetailPage />} />
          <Route path="wlans" element={<WlansPage />} />
          <Route path="wlans/:key" element={<WlanDetailPage />} />
          <Route path="acl" element={<AclPage />} />
          <Route path="acl/rules/:key" element={<AclRuleDetailPage />} />
          <Route path="acl/groups/:key" element={<IpGroupDetailPage />} />
          <Route path="nat" element={<NatPage />} />
          <Route path="nat/:key" element={<NatDetailPage />} />
          <Route path="clients" element={<ClientsPage />} />
          <Route path="clients/:key" element={<ClientDetailPage />} />
          <Route path="documentation" element={<DocumentationPage />} />
          <Route path="documentation/new" element={<DocumentEditPage />} />
          <Route path="documentation/:id" element={<DocumentViewPage />} />
          <Route path="documentation/:id/edit" element={<DocumentEditPage />} />
          <Route path="search" element={<SearchPage />} />
          <Route path="changes" element={<ChangesPage />} />
          <Route path="sync" element={<SyncPage />} />
          <Route path="sync/runs/:id" element={<SyncDetailPage />} />
          <Route path="sync/imports/:id" element={<BackupImportDetailPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="export" element={<ExportPage />} />
          <Route path="sites/:key" element={<SiteDetailPage />} />
          <Route path="controller" element={<ControllerPage />} />
          <Route path="login" element={<Navigate to="/" replace />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </SiteProvider>
  );
}
