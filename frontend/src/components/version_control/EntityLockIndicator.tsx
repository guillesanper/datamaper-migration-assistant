// src/components/version_control/EntityLockIndicator.tsx
import React from 'react';
import { Lock, LockOpen, User, Clock, AlertCircle } from 'lucide-react';
import type { Lock as LockType } from '../../types/version_control_types';
import styles from '../../styles/version_control/lock-indicator.module.css';

interface EntityLockIndicatorProps {
  lock: LockType | null;
  currentUserId?: string;
  variant?: 'badge' | 'inline' | 'detailed';
  className?: string;
  showDetails?: boolean;
}

/**
 * EntityLockIndicator - Visual indicator for entity lock status
 *
 * Displays lock state with color coding:
 * - Green: User owns the lock
 * - Red: Locked by another user
 * - Gray: Not locked
 */
export const EntityLockIndicator: React.FC<EntityLockIndicatorProps> = ({
  lock,
  currentUserId,
  variant = 'badge',
  className = '',
  showDetails = false
}) => {
  if (!lock) {
    // Not locked
    if (variant === 'inline') {
      return (
        <span className={`${styles.inlineIndicator} ${styles.unlocked} ${className}`}>
          <LockOpen size={14} />
          <span>Disponible</span>
        </span>
      );
    }

    return (
      <span className={`${styles.badge} ${styles.unlocked} ${className}`}>
        <LockOpen size={12} />
        Disponible
      </span>
    );
  }

  const isLockedByMe = lock.user_id === currentUserId;
  const statusClass = isLockedByMe ? styles.lockedByMe : styles.lockedByOther;
  const Icon = isLockedByMe ? Lock : AlertCircle;

  // Calculate time remaining
  const expiresAt = new Date(lock.expires_at);
  const now = new Date();
  const timeRemaining = Math.max(0, expiresAt.getTime() - now.getTime());
  const minutesRemaining = Math.floor(timeRemaining / 60000);

  if (variant === 'inline') {
    return (
      <span className={`${styles.inlineIndicator} ${statusClass} ${className}`}>
        <Icon size={14} />
        <span>{isLockedByMe ? 'Editando' : `Bloqueado por ${lock.username}`}</span>
      </span>
    );
  }

  if (variant === 'detailed') {
    return (
      <div className={`${styles.detailedCard} ${statusClass} ${className}`}>
        <div className={styles.detailedHeader}>
          <Icon size={18} />
          <span className={styles.detailedTitle}>
            {isLockedByMe ? 'Estás editando' : 'Bloqueado'}
          </span>
        </div>

        <div className={styles.detailedBody}>
          <div className={styles.detailedItem}>
            <User size={14} />
            <span>{lock.username}</span>
          </div>

          <div className={styles.detailedItem}>
            <Clock size={14} />
            <span>
              {minutesRemaining > 0
                ? `${minutesRemaining} min restantes`
                : 'Expirando...'}
            </span>
          </div>

          {showDetails && lock.reason && (
            <div className={styles.detailedReason}>
              <span className={styles.detailedReasonLabel}>Motivo:</span>
              <span>{lock.reason}</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Badge variant (default)
  return (
    <span className={`${styles.badge} ${statusClass} ${className}`}>
      <Icon size={12} />
      {isLockedByMe ? 'Editando' : `Bloqueado`}
      {showDetails && (
        <span className={styles.badgeDetail}>
          {isLockedByMe ? '' : ` por ${lock.username}`}
        </span>
      )}
    </span>
  );
};

/**
 * Simplified lock status badge
 */
interface LockStatusBadgeProps {
  status: 'active' | 'expired' | 'released';
  className?: string;
}

export const LockStatusBadge: React.FC<LockStatusBadgeProps> = ({ status, className = '' }) => {
  const statusConfig: Record<'active' | 'expired' | 'released', { icon: React.ElementType; label: string; className: string }> = {
    active: {
      icon: Lock,
      label: 'Activo',
      className: styles.statusActive
    },
    expired: {
      icon: AlertCircle,
      label: 'Expirado',
      className: styles.statusExpired
    },
    released: {
      icon: LockOpen,
      label: 'Liberado',
      className: styles.statusReleased
    }
  };

  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <span className={`${styles.statusBadge} ${config.className} ${className}`}>
      <Icon size={12} />
      {config.label}
    </span>
  );
};
