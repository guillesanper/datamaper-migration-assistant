// src/components/dashboard/Sidebar.tsx
import React, { useState, useEffect } from 'react';
import {
  LayoutDashboard,
  Folder,
  Settings,
  Users,
  LogOut,
  ChevronLeft,
  ChevronRight,
  User,
  CreditCard,
  HelpCircle,
  Shield,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../providers/AuthProvider';
import { useNavigate, useLocation } from 'react-router-dom';
import { settingsService } from '../../services/settings_service';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';
import logoImage from '../../assets/logo.png';

interface SidebarProps {
  currentPage: string;
  onPageChange: (page: string) => void;
  isMobileOpen?: boolean;
  onMobileClose?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentPage,
  onPageChange,
  isMobileOpen = false,
  onMobileClose,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [sidebarImgError, setSidebarImgError] = useState(false);
  const { t } = useTranslation('dashboard');

  useEffect(() => {
    const update = () => {
      const isMobile = window.innerWidth <= 1024;
      document.documentElement.style.setProperty(
        '--nav-sidebar-width',
        isMobile ? '0rem' : isCollapsed ? '5rem' : '16rem'
      );
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [isCollapsed]);

  const { logout, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const { data: profile } = useQuery({
    queryKey: ['settings', 'profile'],
    queryFn: () => settingsService.getProfile(),
    staleTime: 5 * 60 * 1000,
  });
  useEffect(() => { setSidebarImgError(false); }, [profile?.avatar_url]);

  const menuItems = [
    { id: 'dashboard', label: t('sidebar.nav.dashboard'), icon: LayoutDashboard },
    { id: 'projects', label: t('sidebar.nav.projects'), icon: Folder },
    { id: 'team', label: t('sidebar.nav.team'), icon: Users },
    { id: 'settings', label: t('sidebar.nav.settings'), icon: Settings },
  ];

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const handlePageChange = (page: string) => {
    onPageChange(page);
  };

  const handleToggle = () => {
    if (isMobileOpen && onMobileClose) {
      onMobileClose();
    } else {
      setIsCollapsed(!isCollapsed);
    }
  };

  return (
    <aside className={`sidebar ${isCollapsed ? 'collapsed' : ''} ${isMobileOpen ? 'mobile-open' : ''}`}>
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <img
            src={logoImage}
            alt="Datamap Logo"
            className="w-8 h-8 rounded-lg object-contain flex-shrink-0"
          />
          {!isCollapsed && <span className="sidebar-logo-text">Datamap</span>}
        </div>

        <button
          onClick={handleToggle}
          className="btn-ghost flex-shrink-0"
          aria-label={
            isMobileOpen
              ? t('sidebar.aria.closeMenu')
              : isCollapsed
              ? t('sidebar.aria.expand')
              : t('sidebar.aria.collapse')
          }
        >
          {isMobileOpen ? (
            <ChevronLeft size={20} />
          ) : (
            isCollapsed ? <ChevronRight size={20} /> : <ChevronLeft size={20} />
          )}
        </button>
      </div>

      <nav className="sidebar-nav">
        {menuItems.map((item) => (
          <div
            key={item.id}
            className={`sidebar-nav-item ${currentPage === item.id ? 'active' : ''}`}
            onClick={() => handlePageChange(item.id)}
          >
            <item.icon size={20} />
            {!isCollapsed && <span>{item.label}</span>}
          </div>
        ))}

        {user?.is_admin && (
          <div
            className={`sidebar-nav-item ${location.pathname.startsWith('/admin') ? 'active' : ''}`}
            onClick={() => navigate('/admin')}
          >
            <Shield size={20} />
            {!isCollapsed && <span>{t('sidebar.nav.admin')}</span>}
          </div>
        )}
      </nav>

      <div className="sidebar-footer">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center gap-3 w-full hover:bg-accent rounded-lg p-2 transition-colors cursor-pointer">
              <div className="member-avatar overflow-hidden">
                {(profile?.avatar_url && !sidebarImgError)
                  ? <img src={`${BASE_URL}${profile.avatar_url}`} alt="" className="w-full h-full object-cover" onError={() => setSidebarImgError(true)} />
                  : user?.email?.[0].toUpperCase()
                }
              </div>
              {!isCollapsed && (
                <div className="flex-1 text-left min-w-0">
                  <p className="text-sm font-medium truncate">
                    {user?.email?.split('@')[0]}
                  </p>
                  <p className="text-xs truncate" style={{ color: 'var(--color-muted-foreground)' }}>
                    {user?.email}
                  </p>
                </div>
              )}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-56" align="end" side="top">
            <DropdownMenuLabel>{t('sidebar.user.account')}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuItem>
                <User className="mr-2 h-4 w-4" />
                <span>{t('sidebar.user.profile')}</span>
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handlePageChange('settings')}>
                <Settings className="mr-2 h-4 w-4" />
                <span>{t('sidebar.user.settings')}</span>
              </DropdownMenuItem>
              <DropdownMenuItem>
                <CreditCard className="mr-2 h-4 w-4" />
                <span>{t('sidebar.user.billing')}</span>
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem>
              <HelpCircle className="mr-2 h-4 w-4" />
              <span>{t('sidebar.user.help')}</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleLogout} variant="destructive">
              <LogOut className="mr-2 h-4 w-4" />
              <span>{t('sidebar.user.logout')}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </aside>
  );
};
