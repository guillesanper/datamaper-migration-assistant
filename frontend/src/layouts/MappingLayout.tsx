// src/layouts/MappingLayout.tsx
import React, { useState } from 'react';
import { Sidebar } from '../components/dashboard/Sidebar';
import { Topbar } from '../components/dashboard/Topbar';
import { Outlet, useNavigate } from 'react-router-dom';
import { FullscreenProvider, useFullscreen } from '../contexts/FullscreenContext';
import '../styles/dashboard/dashboard-index.css';

const MappingLayoutInner: React.FC = () => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const navigate = useNavigate();
  const { isFullscreen } = useFullscreen();

  const handlePageChange = (page: string) => {
    setIsMobileMenuOpen(false);
    navigate(`/${page}`);
  };

  return (
    <div className="dashboard-container">
      {/* Sidebar - Se oculta en modo fullscreen */}
      {!isFullscreen && (
        <Sidebar
          currentPage="mapping"
          onPageChange={handlePageChange}
          isMobileOpen={isMobileMenuOpen}
          onMobileClose={() => setIsMobileMenuOpen(false)}
        />
      )}

      <div className="main-content">
        {/* Topbar - Se oculta en modo fullscreen */}
        {!isFullscreen && (
          <Topbar onMenuClick={() => setIsMobileMenuOpen(true)} />
        )}

        {/* Contenido */}
        <main className={isFullscreen ? "fullscreen-content" : "mapping-page-container"}>
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

export const MappingLayout: React.FC = () => {
  return (
    <FullscreenProvider>
      <MappingLayoutInner />
    </FullscreenProvider>
  );
};