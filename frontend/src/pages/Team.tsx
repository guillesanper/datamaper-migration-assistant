// src/pages/Team.tsx
import React, { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { projectService } from "../services/project_service";
import { LoadingSpinner } from "../components/ui/LoadingSpinner";
import { toast } from "../utils/toast";
import type { Project } from "../types/project_types";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Users, FolderOpen } from "lucide-react";
import { TeamMembers } from "../components/team/TeamMembers";
import { ProjectStats } from "../components/team/ProjectStats";
import { ActivityFeed } from "../components/team/ActivityFeed";
import { CommentsSection } from "../components/team/CommentsSection";
import styles from "../styles/version_control/team.module.css";

export const Team: React.FC = () => {
  const { t } = useTranslation("team");
  const [searchParams, setSearchParams] = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    searchParams.get("project")
  );
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    try {
      setIsLoading(true);
      const projectsData = await projectService.getProjects();
      setProjects(projectsData);

      if (!selectedProjectId && projectsData.length > 0) {
        setSelectedProjectId(projectsData[0].id);
        setSearchParams({ project: projectsData[0].id });
      }
    } catch (error) {
      console.error("Error loading projects:", error);
      toast.error(t("page.errors.load"));
    } finally {
      setIsLoading(false);
    }
  };

  const handleProjectChange = (projectId: string) => {
    setSelectedProjectId(projectId);
    setSearchParams({ project: projectId });
  };

  const selectedProject = projects.find((p) => p.id === selectedProjectId);

  if (isLoading) {
    return <LoadingSpinner fullscreen size="lg" />;
  }

  if (projects.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
        <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-primary/10 to-transparent flex items-center justify-center">
          <FolderOpen className="w-10 h-10 text-muted-foreground/40" />
        </div>
        <div className="text-center max-w-md">
          <h2 className="text-2xl font-semibold mb-2">{t("page.noProjects.title")}</h2>
          <p className="text-muted-foreground text-sm">
            {t("page.noProjects.subtitle")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.teamContainer}>
      {/* Header Sticky */}
      <div className={styles.header}>
        {/* Project Selector */}
        <Select
          value={selectedProjectId || undefined}
          onValueChange={handleProjectChange}
        >
          <SelectTrigger className={`w-full max-w-md ${styles.projectSelector}`}>
            <SelectValue>
              {selectedProject ? (
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary/15 to-primary/5 flex items-center justify-center flex-shrink-0">
                    <Users className="w-4 h-4 text-primary" />
                  </div>
                  <div className="text-left flex-1 min-w-0">
                    <div className="font-semibold text-sm leading-tight truncate">
                      {selectedProject.name}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5 truncate">
                      {selectedProject.origin_db} → {selectedProject.destination_db}
                    </div>
                  </div>
                </div>
              ) : (
                t("projectSelector.placeholder")
              )}
            </SelectValue>
          </SelectTrigger>
          <SelectContent className="w-[var(--radix-select-trigger-width)] max-w-md">
            {projects.map((project) => (
              <SelectItem
                key={project.id}
                value={project.id}
                className="cursor-pointer"
              >
                <div className="flex items-center gap-3 w-full">
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary/15 to-primary/5 flex items-center justify-center flex-shrink-0">
                    <Users className="w-4 h-4 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm truncate">
                      {project.name}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5 truncate">
                      {project.origin_db} → {project.destination_db}
                    </div>
                  </div>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Content */}
      <div className={styles.content}>
        {selectedProject ? (
          <>
            {/* Project Stats */}
            <div className="transition-all duration-300 hover:translate-y-[-2px] mb-6">
              <ProjectStats project={selectedProject} />
            </div>

            {/* Main Grid Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Left Column - Team & Activity (2/3) */}
              <div className="lg:col-span-2 space-y-6">
                <div className="bg-card/60 backdrop-blur-sm border border-border/50 rounded-xl p-5 shadow-sm hover:shadow-md hover:border-primary/20 transition-all duration-300">
                  <TeamMembers
                    project={selectedProject}
                    isOwner={selectedProject.is_owner || false}
                  />
                </div>

                <div className="bg-card/60 backdrop-blur-sm border border-border/50 rounded-xl p-5 shadow-sm hover:shadow-md hover:border-primary/20 transition-all duration-300">
                  <ActivityFeed projectId={selectedProject.id} limit={15} />
                </div>
              </div>

              {/* Right Column - Comments (1/3, sticky) */}
              <div className="lg:col-span-1">
                <div className={styles.stickyPanel}>
                  <CommentsSection
                    entityId={selectedProject.id}
                    entityType="project"
                    projectId={selectedProject.id}
                  />
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-muted/50 to-transparent flex items-center justify-center mx-auto mb-3">
                <FolderOpen className="w-8 h-8 text-muted-foreground/30" />
              </div>
              <p className="text-sm text-muted-foreground">
                {t("projectSelector.placeholder")}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
