// src/layouts/DashboardLayout.tsx
import React, { useState } from 'react';
import { Sidebar } from '../components/dashboard/Sidebar';
import { Topbar } from '../components/dashboard/Topbar';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import '../styles/dashboard/dashboard-index.css';

export const DashboardLayout: React.FC = () => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  // Determine current page from route
  const getCurrentPage = () => {
    const path = location.pathname.replace('/', '');
    return path || 'dashboard';
  };

  const handlePageChange = (page: string) => {
    setIsMobileMenuOpen(false);
    navigate(`/${page}`);
  };

  return (
    <div className="dashboard-container">
      <Sidebar
        currentPage={getCurrentPage()}
        onPageChange={handlePageChange}
        isMobileOpen={isMobileMenuOpen}
        onMobileClose={() => setIsMobileMenuOpen(false)}
      />

      <div className="main-content">
        <Topbar onMenuClick={() => setIsMobileMenuOpen(true)} />

        <main className="page-container">
          <Outlet />
        </main>
      </div>

      {/* Overlay para mobile */}
      {isMobileMenuOpen && (
        <div
          className="sidebar-overlay active"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}
    </div>
  );
};
