// src/components/dashboard/ProjectRow.tsx
import React, { useState } from 'react';
import { Edit2, Trash2, MoreVertical, Users, GitBranch } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { Project, UpdateProjectDTO } from '../../types/project_types';
import { EditProjectModal } from './modals/EditProjectModal';
import { DeleteConfirmModal } from './modals/DeleteConfirmModal';
import { MembersModal } from './modals/MembersModal';
import { projectService } from '../../services/project_service';
import { useNavigate } from 'react-router-dom';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';

interface ProjectRowProps {
  project: Project;
  onUpdate: () => void;
  migrateMode?: boolean;
}

export const ProjectRow: React.FC<ProjectRowProps> = ({ project, onUpdate, migrateMode = false }) => {
  const { t, i18n } = useTranslation('dashboard');
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isMembersModalOpen, setIsMembersModalOpen] = useState(false);
  const navigate = useNavigate();

  const formatDate = (dateString: string): string => {
    try {
      const date = new Date(dateString);
      return new Intl.DateTimeFormat(i18n.language, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      }).format(date);
    } catch {
      return 'N/A';
    }
  };

  const handleEdit = async (projectId: string, data: UpdateProjectDTO) => {
    await projectService.updateProject(projectId, data);
  };

  const handleDelete = async (projectId: string) => {
    await projectService.deleteProject(projectId);
  };

  const handleRowClick = () => {
    const url = migrateMode
      ? `/projects/${project.id}/mapping?action=migrate`
      : `/projects/${project.id}/mapping`;
    navigate(url);
  };

  const renderStatus = () => {
    const statusKey = `projectRow.status.${project.status}` as const;
    return (
      <span className={`project-status ${project.status}`}>
        ● {t(statusKey)}
      </span>
    );
  };

  return (
    <>
      <tr className="project-row cursor-pointer" 
          onClick={handleRowClick}
      >
        <td>
          <div>
            <p className="project-name">{project.name}</p>
            {project.description && (
              <p className="project-description">{project.description}</p>
            )}
          </div>
        </td>

        <td>{renderStatus()}</td>

        <td>
          <div className="text-sm">
            <div className="text-muted-foreground">
              <span className="font-medium">{t('projectRow.dbOrigin')}:</span> {project.origin_db}
            </div>
            <div className="text-muted-foreground">
              <span className="font-medium">{t('projectRow.dbDest')}:</span> {project.destination_db}
            </div>
          </div>
        </td>

        <td>
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-muted rounded-full h-2 overflow-hidden">
              <div 
                className="bg-primary h-full transition-all duration-300"
                style={{ width: `${project.progress}%` }}
              />
            </div>
            <span className="text-sm text-muted-foreground">{project.progress}%</span>
          </div>
        </td>

        <td>
          <span className="font-medium">${project.budget.toLocaleString()}</span>
        </td>

        <td>
          <span className="text-sm text-muted-foreground">
            {formatDate(project.updated_at)}
          </span>
        </td>

        <td>
          <div className="project-actions" onClick={(e) => e.stopPropagation()}> {/* AGREGADO: stopPropagation */}
            {project.is_owner ? (
              <>
                <button 
                  className="btn-icon"
                  title={t('projectRow.actions.edit')}
                  onClick={(e) => {
                    e.stopPropagation();
                    setIsEditModalOpen(true);
                  }}
                >
                  <Edit2 size={16} />
                </button>
                <button 
                  className="btn-icon btn-icon-danger"
                  title={t('projectRow.actions.delete')}
                  onClick={(e) => {
                    e.stopPropagation();
                    setIsDeleteModalOpen(true);
                  }}
                >
                  <Trash2 size={16} />
                </button>
              </>
            ) : (
              <span className="text-xs text-muted-foreground px-2 py-1 bg-muted rounded">
                {t('projectRow.badge.member')}
              </span>
            )}
            
            {/* Menú desplegable */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button 
                  className="btn-icon"
                  title={t('projectRow.moreOptions')}
                  onClick={(e) => e.stopPropagation()}
                >
                  <MoreVertical size={16} />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {project.is_owner && (
                  <>
                    <DropdownMenuItem onClick={() => setIsMembersModalOpen(true)}>
                      <Users className="mr-2 h-4 w-4" />
                      <span>{t('projectRow.actions.members')}</span>
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                  </>
                )}
                <DropdownMenuItem onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/team?project=${project.id}`);
                }}>
                  <Users className="mr-2 h-4 w-4" />
                  <span>{t('projectRow.actions.team')}</span>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/projects/${project.id}/versions`);
                }}>
                  <GitBranch className="mr-2 h-4 w-4" />
                  <span>{t('projectRow.actions.versions')}</span>
                </DropdownMenuItem>
                {!project.is_owner && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => console.log('Leave project')}
                      variant="destructive"
                    >
                      {t('projectRow.actions.leave')}
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </td>
      </tr>

      {/* Modal de edición */}
      <EditProjectModal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        onSuccess={() => {
          console.log('Proyecto actualizado exitosamente');
          onUpdate();
        }}
        onSubmit={handleEdit}
        project={project}
      />

      {/* Modal de eliminación */}
      <DeleteConfirmModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirm={async (projectId) => {
          await handleDelete(projectId);
          onUpdate();
        }}
        project={project}
      />

      {/* Modal de miembros */}
      {project.is_owner && (
        <MembersModal
          isOpen={isMembersModalOpen}
          onClose={() => setIsMembersModalOpen(false)}
          project={project}
        />
      )}
    </>
  );
};