import React, { Suspense, lazy } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { CircularProgress, Box } from '@mui/material';
import Layout from './components/Layout';
import { ColorModeProvider } from './contexts/ColorModeContext';
import { AccountProvider } from './contexts/AccountContext';
import { LoadingProvider } from './contexts/LoadingContext';
import GlobalLoadingIndicator from './components/GlobalLoadingIndicator';

// Lazy load page components for code splitting
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Account = lazy(() => import('./pages/Account'));
const AccountsList = lazy(() => import('./pages/AccountsList'));
const Orders = lazy(() => import('./pages/Orders'));
const StockResearch = lazy(() => import('./pages/StockResearch'));

// Loading fallback component
const PageLoader = () => (
  <Box display="flex" justifyContent="center" alignItems="center" minHeight="50vh">
    <CircularProgress />
  </Box>
);

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { 
        index: true, 
        element: (
          <Suspense fallback={<PageLoader />}>
            <AccountsList />
          </Suspense>
        )
      },
      { 
        path: 'dashboard', 
        element: (
          <Suspense fallback={<PageLoader />}>
            <Dashboard />
          </Suspense>
        )
      },
      { 
        path: 'research', 
        element: (
          <Suspense fallback={<PageLoader />}>
            <StockResearch />
          </Suspense>
        )
      },
      { 
        path: 'orders', 
        element: (
          <Suspense fallback={<PageLoader />}>
            <Orders />
          </Suspense>
        )
      },
      { 
        path: 'account', 
        element: (
          <Suspense fallback={<PageLoader />}>
            <Account />
          </Suspense>
        )
      },
    ],
  },
]);

const App: React.FC = () => {
  return (
    <ColorModeProvider>
      <LoadingProvider>
        <AccountProvider>
          <GlobalLoadingIndicator variant="topbar" showDetails={true} />
          <RouterProvider router={router} />
        </AccountProvider>
      </LoadingProvider>
    </ColorModeProvider>
  );
};

export default App;
