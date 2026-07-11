// src/pages/auth/Login.tsx
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../providers/AuthProvider";
import { Database, Mail, Lock, ArrowRight, AlertCircle, CheckCircle } from "lucide-react";
import "../../styles/auth.css";

export const Login: React.FC = () => {
  const navigate = useNavigate();
  const { login, loading, error, clearError } = useAuth();
  const { t } = useTranslation(["auth", "common"]);

  const [formData, setFormData] = useState({
    identifier: "",
    password: "",
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

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (!formData.identifier.trim() || !formData.password.trim()) {
      setLocalError(t("validation.fields.required"));
      return;
    }

    try {
      await login(formData.identifier, formData.password);
      setSuccess(true);
      setTimeout(() => {
        navigate("/dashboard");
      }, 1500);
    } catch (err: unknown) {
      const errMessage = err instanceof Error ? err.message : "";
      const errData = (err as { data?: { email?: string } })?.data;
      if (errMessage.includes("verificar") || error?.includes("verificar")) {
        const userEmail =
          errData?.email ||
          (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.identifier)
            ? formData.identifier
            : null);

        setTimeout(() => {
          navigate("/verify", {
            state: {
              email: userEmail,
              message: t("messages.verifyEmailFirst"),
            },
          });
        }, 2000);
      }
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
                <div className="feature-icon">✔</div>
                <span>{t("brand.feature.visual")}</span>
              </div>
              <div className="feature-item">
                <div className="feature-icon">✔</div>
                <span>{t("brand.feature.multidb")}</span>
              </div>
              <div className="feature-item">
                <div className="feature-icon">✔</div>
                <span>{t("brand.feature.validation")}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="auth-form-panel">
          <div className="auth-form-container">
            <div className="auth-header">
              <h2>{t("page.login.title")}</h2>
              <p>{t("page.login.subtitle")}</p>
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
                <span>{t("messages.loginSuccess")}</span>
              </div>
            )}

            <form className="auth-form" onSubmit={handleSubmit}>
              <div className="form-group">
                <label htmlFor="identifier">{t("form.usernameOrEmail.label")}</label>
                <div className="input-wrapper">
                  <Mail size={20} className="input-icon" />
                  <input
                    id="identifier"
                    type="text"
                    name="identifier"
                    value={formData.identifier}
                    onChange={handleChange}
                    placeholder={t("form.usernameOrEmail.placeholder")}
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
                  />
                </div>
              </div>

              <div className="form-footer">
                <a href="/forgot-password" className="forgot-link">
                  {t("actions.forgotPassword")}
                </a>
              </div>

              <button
                type="submit"
                className="submit-button"
                disabled={loading || success}
              >
                {loading ? (
                  <>
                    <span className="loading-spinner"></span>
                    {t("actions.loginLoading")}
                  </>
                ) : success ? (
                  <>
                    <CheckCircle size={20} />
                    {t("actions.loginSuccess")}
                  </>
                ) : (
                  <>
                    {t("actions.login")}
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
                {t("actions.noAccount")}{" "}
                <a href="/register" className="link-primary">
                  {t("actions.register")}
                </a>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
