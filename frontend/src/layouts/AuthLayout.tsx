// src/layouts/AuthLayout.tsx
import React from "react";
import { Outlet } from "react-router-dom";
import { useTheme } from "../providers/ThemeProvider";
import { ThemeSwitcher } from "@/components/ui/shadcn-io/theme-switcher"; // Asegúrate de la ruta correcta
import "../styles/auth.css";

export const AuthLayout: React.FC = () => {
  const { theme, setTheme } = useTheme();

  return (
    <div className="auth-layout">
      <ThemeSwitcher 
        value={theme as 'light' | 'dark' | 'system'}
        onChange={setTheme}
        className="theme-switcher"
      />
      <Outlet />
    </div>
  );
};