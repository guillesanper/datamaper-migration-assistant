// src/components/team/TeamMembers.tsx
import React, { useState, useEffect } from 'react';
import { UserPlus, Trash2, Crown, Shield, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui/button';
import { projectService } from '../../services/project_service';
import type { Project, ProjectMember, ProjectRole } from '../../types/project_types';
import { toast } from '../../utils/toast';
import { useAuth } from '../../providers/AuthProvider';

interface TeamMembersProps {
  project: Project;
  isOwner: boolean;
}

export const TeamMembers: React.FC<TeamMembersProps> = ({ project, isOwner }) => {
  const { t } = useTranslation<['team', 'common']>(['team', 'common']);
  const { user } = useAuth();
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isAdding, setIsAdding] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newMemberEmail, setNewMemberEmail] = useState('');
  const [newMemberRole, setNewMemberRole] = useState<ProjectRole>('viewer');

  useEffect(() => {
    loadMembers();
  }, [project.id]);

  const loadMembers = async () => {
    try {
      setIsLoading(true);
      const data = await projectService.getProjectMembers(project.id);
      setMembers(data);
    } catch (error: unknown) {
      console.error('Error loading members:', error);
      if (!isOwner) {
        setMembers([]);
      } else {
        toast.error(t('members.errors.load'));
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddMember = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!newMemberEmail.trim()) {
      toast.error(t('members.errors.emailRequired'));
      return;
    }

    try {
      setIsAdding(true);
      await projectService.addMember(project.id, newMemberEmail.trim(), newMemberRole);
      toast.success(t('members.success.added'));
      setNewMemberEmail('');
      setNewMemberRole('viewer');
      setShowAddForm(false);
      await loadMembers();
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : t('members.errors.add'));
    } finally {
      setIsAdding(false);
    }
  };

  const handleRemoveMember = async (userId: string, email: string) => {
    if (!window.confirm(t('members.removeConfirm', { email }))) return;

    try {
      await projectService.removeMember(project.id, userId);
      toast.success(t('members.success.removed'));
      await loadMembers();
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : t('members.errors.remove'));
    }
  };

  const handleUpdateRole = async (userId: string, newRole: ProjectRole) => {
    try {
      await projectService.updateMemberRole(project.id, userId, newRole);
      toast.success(t('members.success.roleUpdated'));
      setMembers(prev =>
        prev.map(m => m.user_id === userId ? { ...m, role: newRole } : m)
      );
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : t('members.errors.updateRole'));
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!isOwner) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold">{t('members.title')}</h3>
            <p className="text-sm text-muted-foreground">
              {t('members.teamInfo')}
            </p>
          </div>
        </div>
        <div className="text-center py-8 text-muted-foreground bg-muted/30 rounded-lg">
          <Shield className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="text-sm font-medium">{t('members.restrictedAccess')}</p>
          <p className="text-xs mt-1">
            {t('members.restrictedDesc')}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold">{t('members.title')}</h3>
          <p className="text-sm text-muted-foreground">
            {t('members.count', { count: members.length + 1 })}
          </p>
        </div>
        {!showAddForm && (
          <Button
            onClick={() => setShowAddForm(true)}
            size="sm"
            className="gap-2"
          >
            <UserPlus className="w-4 h-4" />
            {t('members.invite')}
          </Button>
        )}
      </div>

      {/* Add member form */}
      {showAddForm && (
        <form onSubmit={handleAddMember} className="bg-muted/50 rounded-lg p-4 space-y-3">
          <div>
            <label className="text-sm font-medium mb-1 block">
              {t('members.emailOrUsername')}
            </label>
            <input
              type="text"
              value={newMemberEmail}
              onChange={(e) => setNewMemberEmail(e.target.value)}
              placeholder={t('members.emailPlaceholder')}
              className="w-full px-3 py-2 rounded-md border bg-background"
              disabled={isAdding}
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">{t('members.roleLabel')}</label>
            <select
              value={newMemberRole}
              onChange={(e) => setNewMemberRole(e.target.value as ProjectRole)}
              className="w-full px-3 py-2 rounded-md border bg-background"
              disabled={isAdding}
            >
              <option value="viewer">{t('common:roles.viewer')}</option>
              <option value="editor">{t('common:roles.editor')}</option>
            </select>
          </div>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={isAdding}>
              {isAdding ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {t('members.addingBtn')}
                </>
              ) : (
                t('members.addBtn')
              )}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                setShowAddForm(false);
                setNewMemberEmail('');
                setNewMemberRole('viewer');
              }}
              disabled={isAdding}
            >
              {t('common:actions.cancel')}
            </Button>
          </div>
        </form>
      )}

      {/* Members list */}
      <div className="space-y-2">
        {/* Project owner */}
        <div className="flex items-center justify-between p-3 bg-gradient-to-r from-yellow-500/10 to-transparent border border-yellow-500/20 rounded-lg">
          <div className="flex items-center gap-3 flex-1">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-yellow-500/20 to-yellow-600/10 flex items-center justify-center">
              <Crown className="w-5 h-5 text-yellow-600 dark:text-yellow-500" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium truncate">
                {user?.email} {isOwner && t('members.you')}
              </p>
              <p className="text-xs text-muted-foreground">
                {t('members.projectCreator')}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 bg-yellow-500/10 border border-yellow-500/20 rounded-full">
            <Crown className="w-4 h-4 text-yellow-600 dark:text-yellow-500" />
            <span className="text-sm font-semibold text-yellow-700 dark:text-yellow-500">
              {t('members.ownerBadge')}
            </span>
          </div>
        </div>

        {/* Other members */}
        {members.map((member) => (
          <div
            key={member.user_id}
            className="flex items-center justify-between p-3 bg-card border rounded-lg hover:bg-muted/50 transition-colors"
          >
            <div className="flex items-center gap-3 flex-1">
              <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center font-semibold">
                {member.email[0].toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{member.email}</p>
                {member.username && (
                  <p className="text-sm text-muted-foreground truncate">
                    @{member.username}
                  </p>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <select
                value={member.role}
                onChange={(e) =>
                  handleUpdateRole(member.user_id, e.target.value as ProjectRole)
                }
                className="px-2 py-1 text-sm rounded border bg-background"
              >
                <option value="viewer">{t('common:roles.viewer')}</option>
                <option value="editor">{t('common:roles.editor')}</option>
              </select>

              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleRemoveMember(member.user_id, member.email)}
                className="text-destructive hover:text-destructive hover:bg-destructive/10"
              >
                <Trash2 className="w-4 h-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>

      {members.length === 0 && (
        <div className="text-center py-8 text-muted-foreground bg-muted/30 rounded-lg">
          <p className="text-sm">{t('members.empty.title')}</p>
          <p className="text-xs mt-1">{t('members.empty.subtitle')}</p>
        </div>
      )}
    </div>
  );
};
