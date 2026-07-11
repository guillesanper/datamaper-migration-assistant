// src/components/dashboard/MembersModal.tsx
import React, { useState, useEffect } from 'react';
import { X, Loader2, UserPlus, Trash2, Crown, User as UserIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/button';
import { projectService } from '../../../services/project_service';
import type { Project, ProjectMember, ProjectRole } from '../../../types/project_types';

interface MembersModalProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project | null;
}

interface AddMemberForm {
  identifier: string;
  role: ProjectRole;
}

export const MembersModal: React.FC<MembersModalProps> = ({
  isOpen,
  onClose,
  project,
}) => {
  const { t } = useTranslation(['dashboard', 'common']);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string>('');

  const [isAdding, setIsAdding] = useState(false);
  const [addForm, setAddForm] = useState<AddMemberForm>({
    identifier: '',
    role: 'viewer',
  });
  const [addError, setAddError] = useState<string>('');

  const [editingRoles, setEditingRoles] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen && !isLoading) {
        handleClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, isLoading]);

  useEffect(() => {
    if (isOpen && project) {
      loadMembers();
    }
  }, [isOpen, project]);

  const loadMembers = async () => {
    if (!project) return;

    setIsLoading(true);
    setError('');

    try {
      const data = await projectService.getProjectMembers(project.id);
      setMembers(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('dashboard:modals.members.errors.load'));
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!project) return;

    if (!addForm.identifier.trim()) {
      setAddError(t('dashboard:modals.members.emailRequired'));
      return;
    }

    setIsAdding(true);
    setAddError('');

    try {
      await projectService.addMember(
        project.id,
        addForm.identifier.trim(),
        addForm.role
      );

      setAddForm({ identifier: '', role: 'viewer' });
      await loadMembers();
    } catch (err: unknown) {
      setAddError(err instanceof Error ? err.message : t('dashboard:modals.members.errors.add'));
    } finally {
      setIsAdding(false);
    }
  };

  const handleUpdateRole = async (userId: string, newRole: ProjectRole) => {
    if (!project) return;

    setEditingRoles(prev => ({ ...prev, [userId]: true }));

    try {
      await projectService.updateMemberRole(project.id, userId, newRole);

      setMembers(prev =>
        prev.map(member =>
          member.user_id === userId ? { ...member, role: newRole } : member
        )
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('dashboard:modals.members.errors.updateRole'));
    } finally {
      setEditingRoles(prev => ({ ...prev, [userId]: false }));
    }
  };

  const handleRemoveMember = async (userId: string, memberEmail: string) => {
    if (!project) return;

    const confirmRemove = window.confirm(
      t('dashboard:modals.members.removeConfirm', { email: memberEmail })
    );

    if (!confirmRemove) return;

    try {
      await projectService.removeMember(project.id, userId);
      setMembers(prev => prev.filter(member => member.user_id !== userId));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('dashboard:modals.members.errors.remove'));
    }
  };

  const handleClose = () => {
    setAddForm({ identifier: '', role: 'viewer' });
    setAddError('');
    setError('');
    onClose();
  };

  if (!isOpen || !project) return null;

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content modal-members" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2 className="modal-title">{t('dashboard:modals.members.title')}</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {project.name}
            </p>
          </div>
          <button
            onClick={handleClose}
            className="btn-icon"
            disabled={isLoading}
            aria-label={t('common:actions.close')}
          >
            <X size={20} />
          </button>
        </div>

        <div className="modal-body">
          {error && (
            <div className="alert alert-error mb-4">
              {error}
            </div>
          )}

          <div className="add-member-section">
            <h3 className="add-member-title">
              <UserPlus size={16} />
              {t('dashboard:modals.members.addSection')}
            </h3>

            <form onSubmit={handleAddMember} className="add-member-form">
              <input
                type="text"
                className="form-input add-member-input"
                placeholder={t('dashboard:modals.members.emailPlaceholder')}
                value={addForm.identifier}
                onChange={(e) => {
                  setAddForm(prev => ({ ...prev, identifier: e.target.value }));
                  if (addError) setAddError('');
                }}
                disabled={isAdding}
              />

              <select
                className="form-input role-select-small"
                value={addForm.role}
                onChange={(e) =>
                  setAddForm(prev => ({ ...prev, role: e.target.value as ProjectRole }))
                }
                disabled={isAdding}
              >
                <option value="viewer">{t('common:roles.viewer')}</option>
                <option value="editor">{t('common:roles.editor')}</option>
              </select>

              <Button
                type="submit"
                className="add-member-button"
                disabled={isAdding || !addForm.identifier.trim()}
              >
                {isAdding ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  t('dashboard:modals.members.addBtn')
                )}
              </Button>

              {addError && (
                <span className="form-error add-member-error">{addError}</span>
              )}
            </form>
          </div>

          <div className="members-section">
            <h3 className="text-sm font-semibold mb-3">
              {t('dashboard:modals.members.membersSection', { count: members.length + 1 })}
            </h3>

            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 size={32} className="animate-spin text-primary" />
              </div>
            ) : (
              <div className="members-list">
                <div className="member-item owner">
                  <div className="member-avatar">
                    <Crown size={16} />
                  </div>
                  <div className="member-info">
                    <p className="member-name">
                      {t('dashboard:modals.members.you')}
                    </p>
                    <p className="member-email">{t('dashboard:modals.members.projectCreator')}</p>
                  </div>
                  <div className="member-role">
                    <span className="role-badge owner">{t('dashboard:modals.members.ownerBadge')}</span>
                  </div>
                </div>

                {members.map((member) => (
                  <div key={member.user_id} className="member-item">
                    <div className="member-avatar">
                      {member.email[0].toUpperCase()}
                    </div>
                    <div className="member-info">
                      <p className="member-name">
                        {member.username || member.email.split('@')[0]}
                      </p>
                      <p className="member-email">{member.email}</p>
                    </div>
                    <div className="member-actions">
                      <select
                        className="role-select"
                        value={member.role}
                        onChange={(e) =>
                          handleUpdateRole(member.user_id, e.target.value as ProjectRole)
                        }
                        disabled={editingRoles[member.user_id]}
                      >
                        <option value="viewer">{t('common:roles.viewer')}</option>
                        <option value="editor">{t('common:roles.editor')}</option>
                      </select>

                      <button
                        className="btn-icon btn-icon-danger"
                        onClick={() => handleRemoveMember(member.user_id, member.email)}
                        disabled={editingRoles[member.user_id]}
                        title={t('common:actions.delete')}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                ))}

                {members.length === 0 && (
                  <div className="text-center py-8 text-muted-foreground">
                    <UserIcon size={48} className="mx-auto mb-2 opacity-20" />
                    <p className="text-sm">
                      {t('dashboard:modals.members.empty')}
                    </p>
                    <p className="text-xs mt-1">
                      {t('dashboard:modals.members.emptyHint')}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="modal-footer">
            <Button
              type="button"
              variant="outline"
              onClick={handleClose}
            >
              {t('dashboard:modals.members.closeBtn')}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
