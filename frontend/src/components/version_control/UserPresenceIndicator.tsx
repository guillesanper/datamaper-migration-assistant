// src/components/version_control/UserPresenceIndicator.tsx
import React from 'react';
import { User, Clock } from 'lucide-react';
import { type OnlineUser } from '../../types/version_control_types';
import styles from '../../styles/version_control/presence-indicator.module.css';

interface UserPresenceIndicatorProps {
  user: OnlineUser;
  variant?: 'dot' | 'badge' | 'card';
  showLastSeen?: boolean;
  className?: string;
}

/**
 * UserPresenceIndicator - Shows user online/offline status
 *
 * Variants:
 * - dot: Small colored dot (8px)
 * - badge: Dot with username
 * - card: Full card with avatar and details
 */
export const UserPresenceIndicator: React.FC<UserPresenceIndicatorProps> = ({
  user,
  variant = 'badge',
  showLastSeen = false,
  className = ''
}) => {
  const isOnline = user.status === 'online';
  const statusClass = isOnline ? styles.online : styles.offline;

  // Format last seen time
  const formatLastSeen = (timestamp: string): string => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Ahora mismo';
    if (diffMins < 60) return `Hace ${diffMins} min`;

    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `Hace ${diffHours}h`;

    const diffDays = Math.floor(diffHours / 24);
    return `Hace ${diffDays}d`;
  };

  if (variant === 'dot') {
    return (
      <span
        className={`${styles.dot} ${statusClass} ${className}`}
        title={`${user.username} - ${isOnline ? 'En línea' : 'Desconectado'}`}
      />
    );
  }

  if (variant === 'badge') {
    return (
      <span className={`${styles.badge} ${className}`}>
        <span className={`${styles.dot} ${statusClass}`} />
        <span className={styles.username}>{user.username}</span>
        {showLastSeen && !isOnline && user.last_seen && (
          <span className={styles.lastSeen}>
            {formatLastSeen(user.last_seen)}
          </span>
        )}
      </span>
    );
  }

  // Card variant
  return (
    <div className={`${styles.card} ${className}`}>
      <div className={styles.avatarContainer}>
        <div className={styles.avatar}>
          <User size={20} />
        </div>
        <span className={`${styles.dot} ${statusClass} ${styles.dotAbsolute}`} />
      </div>

      <div className={styles.cardContent}>
        <div className={styles.cardHeader}>
          <span className={styles.cardUsername}>{user.username}</span>
          <span className={`${styles.statusLabel} ${statusClass}`}>
            {isOnline ? 'En línea' : 'Desconectado'}
          </span>
        </div>

        {showLastSeen && !isOnline && user.last_seen && (
          <div className={styles.cardFooter}>
            <Clock size={12} />
            <span>{formatLastSeen(user.last_seen)}</span>
          </div>
        )}

        {isOnline && user.current_page && (
          <div className={styles.cardFooter}>
            <span className={styles.currentPage}>Viendo: {user.current_page}</span>
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * UserPresenceList - Shows list of online users
 */
interface UserPresenceListProps {
  users: OnlineUser[];
  maxDisplay?: number;
  variant?: 'dot' | 'badge' | 'card';
  className?: string;
}

export const UserPresenceList: React.FC<UserPresenceListProps> = ({
  users,
  maxDisplay = 5,
  variant = 'badge',
  className = ''
}) => {
  const displayUsers = users.slice(0, maxDisplay);
  const remainingCount = users.length - maxDisplay;

  if (variant === 'dot') {
    return (
      <div className={`${styles.dotList} ${className}`}>
        {displayUsers.map((user) => (
          <UserPresenceIndicator key={user.user_id} user={user} variant="dot" />
        ))}
        {remainingCount > 0 && (
          <span className={styles.remainingCount} title={`${remainingCount} más`}>
            +{remainingCount}
          </span>
        )}
      </div>
    );
  }

  if (variant === 'badge') {
    return (
      <div className={`${styles.badgeList} ${className}`}>
        {displayUsers.map((user) => (
          <UserPresenceIndicator key={user.user_id} user={user} variant="badge" />
        ))}
        {remainingCount > 0 && (
          <span className={styles.badge}>
            <span className={styles.username}>+{remainingCount} más</span>
          </span>
        )}
      </div>
    );
  }

  // Card variant
  return (
    <div className={`${styles.cardList} ${className}`}>
      {displayUsers.map((user) => (
        <UserPresenceIndicator key={user.user_id} user={user} variant="card" showLastSeen />
      ))}
      {remainingCount > 0 && (
        <div className={styles.cardListFooter}>
          Y {remainingCount} usuario{remainingCount > 1 ? 's' : ''} más
        </div>
      )}
    </div>
  );
};

/**
 * Simple online count indicator
 */
interface OnlineCountProps {
  count: number;
  className?: string;
}

export const OnlineCount: React.FC<OnlineCountProps> = ({ count, className = '' }) => {
  return (
    <div className={`${styles.onlineCount} ${className}`}>
      <span className={`${styles.dot} ${styles.online}`} />
      <span className={styles.countText}>
        {count} en línea
      </span>
    </div>
  );
};
