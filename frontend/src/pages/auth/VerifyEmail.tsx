// src/pages/auth/VerifyEmail.tsx
import React, { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../providers/AuthProvider";
import { Mail, ArrowRight, AlertCircle, CheckCircle } from "lucide-react";
import { CodeInput } from "../../components/auth/CodeInput";
import "../../styles/auth.css";

export const VerifyEmail: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { verifyCode, resendCode, loading, error, clearError } = useAuth();
  const { t } = useTranslation(["auth", "common"]);

  const stateData = (location.state as { email?: string; message?: string }) || {};
  const emailFromState = stateData.email;
  const messageFromState = stateData.message;

  const [email, setEmail] = useState(emailFromState || "");
  const [showEmailInput, setShowEmailInput] = useState(!emailFromState);
  const [code, setCode] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [resendSuccess, setResendSuccess] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);

  useEffect(() => {
    if (resendCooldown > 0) {
      const timer = setTimeout(() => setResendCooldown(resendCooldown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [resendCooldown]);

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setEmail(e.target.value);
    setLocalError(null);
    clearError();
  };

  const handleCodeChange = (newCode: string) => {
    setCode(newCode.toUpperCase());
    setLocalError(null);
    clearError();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!email.trim()) {
      setLocalError(t("validation.email.required"));
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      setLocalError(t("validation.email.invalid"));
      return;
    }

    if (code.length !== 8) {
      setLocalError(t("validation.code.length"));
      return;
    }

    try {
      await verifyCode(email, code);
      setSuccess(true);
      setTimeout(() => {
        navigate("/projects");
      }, 1500);
    } catch {
      // El error ya está en el contexto
    }
  };

  const handleResendCode = async () => {
    if (resendCooldown > 0) return;

    if (!email.trim()) {
      setLocalError(t("validation.email.first"));
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      setLocalError(t("validation.email.invalid"));
      return;
    }

    try {
      await resendCode(email);
      setResendSuccess(true);
      setResendCooldown(60);
      setShowEmailInput(false);
      setTimeout(() => setResendSuccess(false), 3000);
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
              <Mail size={48} strokeWidth={1.5} />
            </div>
            <h1 className="brand-title">{t("page.verify.title")}</h1>
            <p className="brand-subtitle">
              {t("page.verify.subtitle", { email: email || "" })}
            </p>
            <div className="brand-features">
              <div className="feature-item">
                <div className="feature-icon">📧</div>
                <span>{t("verify.hint.inbox")}</span>
              </div>
              <div className="feature-item">
                <div className="feature-icon">🔒</div>
                <span>{t("verify.hint.validity")}</span>
              </div>
              <div className="feature-item">
                <div className="feature-icon">🔄</div>
                <span>{t("verify.hint.resend")}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="auth-form-panel">
          <div className="auth-form-container">
            <div className="auth-header">
              <h2>{t("page.verify.title")}</h2>
              <p>
                {showEmailInput
                  ? t("verify.enterEmailSubtitle")
                  : t("verify.sentTo", { email })}
              </p>
            </div>

            {messageFromState && (
              <div className="alert alert-error">
                <AlertCircle size={20} />
                <span>{messageFromState}</span>
              </div>
            )}

            {displayError && !messageFromState && (
              <div className="alert alert-error">
                <AlertCircle size={20} />
                <span>{displayError}</span>
              </div>
            )}

            {success && (
              <div className="alert alert-success">
                <CheckCircle size={20} />
                <span>{t("messages.emailVerified")}</span>
              </div>
            )}

            {resendSuccess && (
              <div className="alert alert-success">
                <CheckCircle size={20} />
                <span>{t("messages.codeSent")}</span>
              </div>
            )}

            <form className="auth-form" onSubmit={handleSubmit}>
              {showEmailInput && (
                <div className="form-group">
                  <label htmlFor="email">{t("form.email.label")}</label>
                  <div className="input-wrapper">
                    <Mail size={20} className="input-icon" />
                    <input
                      id="email"
                      type="email"
                      name="email"
                      value={email}
                      onChange={handleEmailChange}
                      placeholder={t("form.email.placeholder")}
                      required
                      disabled={loading || success}
                    />
                  </div>
                  <small className="form-hint">{t("verify.emailHint")}</small>
                </div>
              )}

              <div className="form-group">
                <label htmlFor="code">{t("verify.code.label")}</label>
                <CodeInput
                  value={code}
                  onChange={handleCodeChange}
                  disabled={loading || success}
                  length={8}
                />
                <small className="form-hint">{t("verify.code.hint")}</small>
              </div>

              <button
                type="submit"
                className="submit-button"
                disabled={loading || success || code.length !== 8}
              >
                {loading ? (
                  <>
                    <span className="loading-spinner"></span>
                    {t("actions.verifying")}
                  </>
                ) : success ? (
                  <>
                    <CheckCircle size={20} />
                    {t("actions.verified")}
                  </>
                ) : (
                  <>
                    {t("actions.verify")}
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
                {t("verify.noCode")}{" "}
                <button
                  onClick={handleResendCode}
                  disabled={resendCooldown > 0 || loading}
                  className="link-primary"
                  style={{
                    background: "none",
                    border: "none",
                    cursor: resendCooldown > 0 ? "not-allowed" : "pointer",
                    opacity: resendCooldown > 0 ? 0.5 : 1,
                  }}
                >
                  {resendCooldown > 0
                    ? t("actions.resendCountdown", { seconds: resendCooldown })
                    : t("actions.resendCode")}
                </button>
              </p>
              {!showEmailInput && (
                <p style={{ marginTop: "0.5rem" }}>
                  <button
                    onClick={() => setShowEmailInput(true)}
                    className="link-primary"
                    style={{
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                    }}
                  >
                    {t("actions.changeEmail")}
                  </button>
                </p>
              )}
              <p style={{ marginTop: "0.5rem" }}>
                <a href="/login" className="link-primary">
                  {t("actions.backToLogin")}
                </a>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
