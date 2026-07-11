// src/components/settings/ProfileTab.tsx
import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, Eye, EyeOff, Camera, Trash2 } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { settingsService } from '../../services/settings_service';
import { toast } from '../../utils/toast';
import { secureCleanupState } from '../../utils/secureMemory';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
const MAX_SIZE = 2 * 1024 * 1024; // 2MB

function getAvatarColor(name: string): string {
  const hue = (name.charCodeAt(0) * 37) % 360;
  return `hsl(${hue}, 65%, 50%)`;
}

export const ProfileTab: React.FC = () => {
  const { t } = useTranslation('settings');
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [username, setUsername] = useState('');
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [imgError, setImgError] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [passwordError, setPasswordError] = useState('');

  useEffect(() => {
    return () => {
      secureCleanupState(setCurrentPassword);
      secureCleanupState(setNewPassword);
      secureCleanupState(setConfirmPassword);
    };
  }, []);

  useEffect(() => {
    return () => {
      if (avatarPreview) {
        URL.revokeObjectURL(avatarPreview);
      }
    };
  }, [avatarPreview]);

  const { data: profile, isLoading } = useQuery({
    queryKey: ['settings', 'profile'],
    queryFn: () => settingsService.getProfile(),
  });

  useEffect(() => {
    if (profile) {
      setUsername(profile.username);
    }
  }, [profile]);

  const updateProfileMutation = useMutation({
    mutationFn: (data: { username: string }) => settingsService.updateProfile(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'profile'] });
      toast.success(t('profile.success.updated'));
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const changePasswordMutation = useMutation({
    mutationFn: (data: { current_password: string; new_password: string; confirm_password: string }) =>
      settingsService.changePassword(data),
    onSuccess: () => {
      secureCleanupState(setCurrentPassword);
      secureCleanupState(setNewPassword);
      secureCleanupState(setConfirmPassword);
      toast.success(t('profile.success.passwordUpdated'));
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const uploadAvatarMutation = useMutation({
    mutationFn: (file: File) => settingsService.uploadAvatar(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'profile'] });
      setImgError(false);
      if (avatarPreview) {
        URL.revokeObjectURL(avatarPreview);
      }
      setAvatarPreview(null);
      setSelectedFile(null);
      toast.success(t('profile.success.photoUpdated'));
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const deleteAvatarMutation = useMutation({
    mutationFn: () => settingsService.deleteAvatar(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'profile'] });
      toast.success(t('profile.success.photoRemoved'));
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!ALLOWED_TYPES.includes(file.type)) {
      toast.error(t('profile.error.format'));
      return;
    }
    if (file.size > MAX_SIZE) {
      toast.error(t('profile.error.size'));
      return;
    }

    if (avatarPreview) {
      URL.revokeObjectURL(avatarPreview);
    }
    setAvatarPreview(URL.createObjectURL(file));
    setSelectedFile(file);
    // Reset input so same file can be selected again
    e.target.value = '';
  };

  const handleCancelAvatar = () => {
    if (avatarPreview) {
      URL.revokeObjectURL(avatarPreview);
    }
    setAvatarPreview(null);
    setSelectedFile(null);
  };

  const handlePasswordSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError('');

    if (newPassword.length < 8) {
      setPasswordError(t('profile.validation.passwordMin'));
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError(t('profile.validation.passwordMismatch'));
      return;
    }
    changePasswordMutation.mutate({ current_password: currentPassword, new_password: newPassword, confirm_password: confirmPassword });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={24} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  const avatarSrc = avatarPreview ?? (profile?.avatar_url ? `${BASE_URL}${profile.avatar_url}` : null);
  const displayName = profile?.username || '';

  return (
    <div className="space-y-8 max-w-4xl">
      {/* Avatar */}
      <section className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-5">
          {t('profile.avatarLabel')}
        </h2>
        <div className="flex items-center gap-6">
          {/* Avatar circle */}
          <div className="relative flex-shrink-0">
            <div
              className="w-20 h-20 rounded-full overflow-hidden flex items-center justify-center text-white text-2xl font-semibold"
              style={{ backgroundColor: (avatarSrc && !imgError) ? undefined : getAvatarColor(displayName) }}
            >
              {(avatarSrc && !imgError) ? (
                <img
                  src={avatarSrc}
                  alt=""
                  className="w-full h-full object-cover"
                  onError={() => setImgError(true)}
                />
              ) : (
                <span>{displayName.charAt(0).toUpperCase() || '?'}</span>
              )}
            </div>
          </div>

          {/* Buttons */}
          <div className="flex flex-col gap-2">
            {!selectedFile ? (
              <>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                  className="gap-2"
                >
                  <Camera size={14} />
                  {t('profile.changePhoto')}
                </Button>
                {profile?.avatar_url && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => deleteAvatarMutation.mutate()}
                    disabled={deleteAvatarMutation.isPending}
                    className="gap-2 text-destructive hover:text-destructive"
                  >
                    {deleteAvatarMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                    {t('profile.removePhoto')}
                  </Button>
                )}
              </>
            ) : (
              <>
                <Button
                  type="button"
                  size="sm"
                  onClick={() => selectedFile && uploadAvatarMutation.mutate(selectedFile)}
                  disabled={uploadAvatarMutation.isPending}
                  className="gap-2"
                >
                  {uploadAvatarMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
                  {t('profile.savePhoto')}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleCancelAvatar}
                  disabled={uploadAvatarMutation.isPending}
                >
                  {t('profile.cancelPhoto')}
                </Button>
              </>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept={ALLOWED_TYPES.join(',')}
              className="hidden"
              onChange={handleFileChange}
            />
          </div>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">{t('profile.formats')}</p>
      </section>

      {/* Personal info */}
      <section className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-5">
          {t('profile.section.info')}
        </h2>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">{t('profile.name.label')}</label>
            <Input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t('profile.name.placeholder')}
              className='form-input'
              maxLength={50}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">{t('profile.email.label')}</label>
            <div className="flex items-center gap-2">
              <Input value={profile?.email ?? ''} disabled className="flex-1 form-input" />
              <span
                className={`text-xs px-2 py-1 rounded-full font-medium flex-shrink-0 ${
                  profile?.is_verified
                    ? 'bg-green-100 text-green-800'
                    : 'bg-yellow-100 text-yellow-800'
                }`}
              >
                {profile?.is_verified ? t('profile.email.verified') : t('profile.email.unverified')}
              </span>
            </div>
          </div>
          <Button
            onClick={() => updateProfileMutation.mutate({ username })}
            disabled={updateProfileMutation.isPending || username === profile?.username}
            className="gap-2"
          >
            {updateProfileMutation.isPending && <Loader2 size={14} className="animate-spin" />}
            {t('profile.saveChanges')}
          </Button>
        </div>
      </section>

      {/* Password */}
      <section className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-5">
          {t('profile.changePassword')}
        </h2>
        <form onSubmit={handlePasswordSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">{t('profile.currentPassword')}</label>
            <div className="relative">
              <Input
                type={showCurrent ? 'text' : 'password'}
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                className="form-input"
              />
              <button
                type="button"
                onClick={() => setShowCurrent(!showCurrent)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showCurrent ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">{t('profile.newPassword')}</label>
            <div className="relative">
              <Input
                type={showNew ? 'text' : 'password'}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder={t('profile.newPasswordPlaceholder')}
                autoComplete="new-password"
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setShowNew(!showNew)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showNew ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">{t('profile.confirmPassword')}</label>
            <Input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder={t('profile.confirmPasswordPlaceholder')}
              autoComplete="new-password"
            />
          </div>
          {passwordError && (
            <p className="text-sm text-destructive">{passwordError}</p>
          )}
          <Button
            type="submit"
            disabled={changePasswordMutation.isPending || !currentPassword || !newPassword || !confirmPassword}
            className="gap-2"
          >
            {changePasswordMutation.isPending && <Loader2 size={14} className="animate-spin" />}
            {t('profile.changePassword')}
          </Button>
        </form>
      </section>
    </div>
  );
};
