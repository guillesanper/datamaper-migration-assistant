// src/pages/auth/Register.tsx
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../providers/AuthProvider";
import { Database, Mail, Lock, User, ArrowRight, AlertCircle, CheckCircle } from "lucide-react";
import "../../styles/auth.css";

export const Register: React.FC = () => {
  const navigate = useNavigate();
  const { register, loading, error, clearError } = useAuth();
  const { t } = useTranslation(["auth", "common"]);

  const [formData, setFormData] = useState({
    username: "",
    email: "",
    password: "",
    confirmPassword: "",
  });

  const [localError, setLocalError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
    setLocalError(null);
    clearError();
  };

  const validateForm = (): boolean => {
    if (!formData.username.trim()) {
      setLocalError(t("validation.username.required"));
      return false;
    }

    if (formData.username.length < 3) {
      setLocalError(t("validation.username.min"));
      return false;
    }

    if (!formData.email.trim()) {
      setLocalError(t("validation.email.required"));
      return false;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(formData.email)) {
      setLocalError(t("validation.email.invalid"));
      return false;
    }

    if (!formData.password.trim()) {
      setLocalError(t("validation.password.required"));
      return false;
    }

    if (formData.password.length < 8) {
      setLocalError(t("validation.password.min"));
      return false;
    }

    if (formData.password !== formData.confirmPassword) {
      setLocalError(t("validation.password.mismatch"));
      return false;
    }

    return true;
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    try {
      await register(
        formData.username,
        formData.email,
        formData.password,
        formData.confirmPassword
      );
      setSuccess(true);
      setTimeout(() => {
        navigate("/verify", { state: { email: formData.email } });
      }, 2000);
    } catch {
      // El error ya está en el contexto
    }
  };

  const displayError = localError || error;

  return (
    <div className="auth-container">
      <div className="auth-content">
        <div className="auth-brand-panel">
          <div className="brand-content">
            <div className="brand-icon">
              <Database size={48} strokeWidth={1.5} />
            </div>
            <h1 className="brand-title">{t("brand.title")}</h1>
            <p className="brand-subtitle">{t("brand.subtitle")}</p>
            <div className="brand-features">
              <div className="feature-item">
                <div className="feature-icon">✓</div>
                <span>{t("brand.feature.visual")}</span>
              </div>
              <div className="feature-item">
                <div className="feature-icon">✓</div>
                <span>{t("brand.feature.multidb")}</span>
              </div>
              <div className="feature-item">
                <div className="feature-icon">✓</div>
                <span>{t("brand.feature.validation")}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="auth-form-panel">
          <div className="auth-form-container">
            <div className="auth-header">
              <h2>{t("page.register.title")}</h2>
              <p>{t("page.register.subtitle")}</p>
            </div>

            {displayError && (
              <div className="alert alert-error">
                <AlertCircle size={20} />
                <span>{displayError}</span>
              </div>
            )}

            {success && (
              <div className="alert alert-success">
                <CheckCircle size={20} />
                <span>{t("messages.registerSuccess")}</span>
              </div>
            )}

            <form className="auth-form" onSubmit={handleSubmit}>
              <div className="form-group">
                <label htmlFor="username">{t("form.username.label")}</label>
                <div className="input-wrapper">
                  <User size={20} className="input-icon" />
                  <input
                    id="username"
                    type="text"
                    name="username"
                    value={formData.username}
                    onChange={handleChange}
                    placeholder={t("form.username.placeholder")}
                    required
                    disabled={loading || success}
                    minLength={3}
                  />
                </div>
                <small className="form-hint">{t("form.username.hint")}</small>
              </div>

              <div className="form-group">
                <label htmlFor="email">{t("form.email.label")}</label>
                <div className="input-wrapper">
                  <Mail size={20} className="input-icon" />
                  <input
                    id="email"
                    type="email"
                    name="email"
                    value={formData.email}
                    onChange={handleChange}
                    placeholder={t("form.email.placeholder")}
                    required
                    disabled={loading || success}
                  />
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="password">{t("form.password.label")}</label>
                <div className="input-wrapper">
                  <Lock size={20} className="input-icon" />
                  <input
                    id="password"
                    type="password"
                    name="password"
                    value={formData.password}
                    onChange={handleChange}
                    placeholder={t("form.password.placeholder")}
                    required
                    disabled={loading || success}
                    minLength={8}
                  />
                </div>
                <small className="form-hint">{t("form.password.hint")}</small>
              </div>

              <div className="form-group">
                <label htmlFor="confirmPassword">{t("form.confirmPassword.label")}</label>
                <div className="input-wrapper">
                  <Lock size={20} className="input-icon" />
                  <input
                    id="confirmPassword"
                    type="password"
                    name="confirmPassword"
                    value={formData.confirmPassword}
                    onChange={handleChange}
                    placeholder={t("form.password.placeholder")}
                    required
                    disabled={loading || success}
                  />
                </div>
              </div>

              <button
                type="submit"
                className="submit-button"
                disabled={loading || success}
              >
                {loading ? (
                  <>
                    <span className="loading-spinner"></span>
                    {t("actions.registerLoading")}
                  </>
                ) : success ? (
                  <>
                    <CheckCircle size={20} />
                    {t("actions.registerSuccess")}
                  </>
                ) : (
                  <>
                    {t("actions.register")}
                    <ArrowRight size={20} />
                  </>
                )}
              </button>
            </form>

            <div className="auth-divider">
              <span>{t("common:divider.or")}</span>
            </div>

            <div className="auth-footer">
              <p>
                {t("actions.hasAccount")}{" "}
                <a href="/login" className="link-primary">
                  {t("actions.login")}
                </a>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
