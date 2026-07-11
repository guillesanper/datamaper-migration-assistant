# app/services/project_service.py
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import text

from app.crud import user_crud
from app.crud.project_crud import ProjectCRUD
from app.models.orm.project import ProjectMember


class ProjectService:
    """
    Servicio que maneja la lógica de negocio de proyectos
    Actúa como capa intermedia entre las rutas y el CRUD
    """

    # Límite máximo de proyectos por usuario
    MAX_PROJECTS_PER_USER = 5

    # Estados válidos de proyecto
    VALID_STATUSES = ["active", "paused", "completed"]

    @staticmethod
    def validate_project_data(
        name: str,
        origin_db: str,
        destination_db: str,
        status: str = "active",
        progress: int = 0,
        budget: float = 0.0,
    ):
        """
        Valida los datos de un proyecto

        Raises:
            HTTPException si los datos no son válidos
        """
        if not name or len(name.strip()) < 3:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="El nombre debe tener al menos 3 caracteres",
            )

        if len(name) > 100:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="El nombre no puede exceder 100 caracteres",
            )

        if not origin_db or not origin_db.strip():
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="La base de datos de origen es obligatoria",
            )

        if not destination_db or not destination_db.strip():
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="La base de datos de destino es obligatoria",
            )

        if status not in ProjectService.VALID_STATUSES:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Estado inválido. Debe ser uno de: {', '.join(ProjectService.VALID_STATUSES)}",
            )

        if not 0 <= progress <= 100:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="El progreso debe estar entre 0 y 100",
            )

        if budget < 0:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="El presupuesto no puede ser negativo",
            )

    @staticmethod
    def create_project(
        db,
        user_id: str,
        name: str,
        description: str,
        origin_db: str,
        destination_db: str,
        status: str = "active",
        progress: int = 0,
        budget: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Crea un nuevo proyecto con validaciones de negocio

        Args:
            db: Conexión a la base de datos
            user_id: ID del usuario creador
            name: Nombre del proyecto
            description: Descripción del proyecto
            origin_db: Base de datos de origen
            destination_db: Base de datos de destino
            status: Estado del proyecto
            progress: Progreso del proyecto
            budget: Presupuesto del proyecto

        Returns:
            Dict con los datos del proyecto creado

        Raises:
            HTTPException si no se puede crear el proyecto
        """
        try:
            # Validar datos del proyecto
            ProjectService.validate_project_data(
                name, origin_db, destination_db, status, progress, budget
            )

            # Bloqueo de fila para evitar condiciones de carrera
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:user_id))"), {"user_id": str(user_id)}
            )

            # Verificar límite de proyectos
            count = ProjectCRUD.count_user_projects_orm(db, user_id)

            if count >= ProjectService.MAX_PROJECTS_PER_USER:
                raise HTTPException(
                    status_code=http_status.HTTP_403_FORBIDDEN,
                    detail=f"Has alcanzado el límite máximo de {ProjectService.MAX_PROJECTS_PER_USER} proyectos",
                )

            # Crear el proyecto
            project = ProjectCRUD.create_project_orm(
                db=db,
                owner_id=user_id,
                name=name.strip(),
                description=description.strip() if description else "",
                origin_db=origin_db.strip(),
                destination_db=destination_db.strip(),
                status=status,
                progress=progress,
                budget=budget,
            )

            db.commit()

            # Agregar flag de propietario
            project["is_owner"] = True

            return project

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al crear el proyecto: {str(e)}",
            )

    @staticmethod
    def get_user_projects(
        db,
        user_id: str,
        status_filter: Optional[str] = None,
        sort_by: str = "name",
        sort_order: str = "asc",
    ) -> List[Dict[str, Any]]:
        """
        Obtiene todos los proyectos de un usuario

        Args:
            db: Conexión a la base de datos
            user_id: ID del usuario
            status_filter: Filtro opcional por estado
            sort_by: Campo por el cual ordenar
            sort_order: Orden de ordenamiento

        Returns:
            Lista de proyectos
        """
        try:
            projects = ProjectCRUD.get_user_projects_orm(
                db=db, user_id=user_id, status=status_filter, sort_by=sort_by, sort_order=sort_order
            )

            return projects

        except Exception as e:
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al obtener proyectos: {str(e)}",
            )

    @staticmethod
    def get_project_by_id(db, project_id: str, user_id: str) -> Dict[str, Any]:
        """
        Obtiene un proyecto por su ID con verificación de acceso

        Args:
            db: Conexión a la base de datos
            project_id: ID del proyecto
            user_id: ID del usuario solicitante

        Returns:
            Dict con los datos del proyecto

        Raises:
            HTTPException si no existe o no tiene acceso
        """
        project = ProjectCRUD.get_project_by_id_orm(db, project_id)

        if not project:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado"
            )

        # Verificar acceso
        access = ProjectCRUD.check_user_access_orm(db, project_id, user_id)

        if not access:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este proyecto",
            )

        project["is_owner"] = access["is_owner"]
        if not access["is_owner"]:
            project["member_role"] = access["role"]

        return project

    @staticmethod
    def update_project(db, project_id: str, user_id: str, **kwargs) -> Dict[str, Any]:
        """
        Actualiza un proyecto con validaciones

        Args:
            db: Conexión a la base de datos
            project_id: ID del proyecto
            user_id: ID del usuario solicitante
            **kwargs: Campos a actualizar

        Returns:
            Dict con los datos del proyecto actualizado

        Raises:
            HTTPException si no tiene permisos o datos inválidos
        """
        try:
            # Verificar que el proyecto existe
            project = ProjectCRUD.get_project_by_id_orm(db, project_id)

            if not project:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado"
                )

            # Verificar permisos (solo owner o editor pueden actualizar)
            access = ProjectCRUD.check_user_access_orm(db, project_id, user_id)

            if not access:
                raise HTTPException(
                    status_code=http_status.HTTP_403_FORBIDDEN,
                    detail="No tienes acceso a este proyecto",
                )

            # Los viewers no pueden editar
            if not access["is_owner"] and access["role"] == "viewer":
                raise HTTPException(
                    status_code=http_status.HTTP_403_FORBIDDEN,
                    detail="No tienes permisos para editar este proyecto",
                )

            # Validar datos si se están actualizando
            if any(
                k in kwargs
                for k in ["name", "origin_db", "destination_db", "status", "progress", "budget"]
            ):
                # Usar valores actuales si no se proporcionan
                name = kwargs.get("name", project["name"])
                origin_db = kwargs.get("origin_db", project["origin_db"])
                destination_db = kwargs.get("destination_db", project["destination_db"])
                status_val = kwargs.get("status", project["status"])
                progress = kwargs.get("progress", project["progress"])
                budget = kwargs.get("budget", project["budget"])

                ProjectService.validate_project_data(
                    name, origin_db, destination_db, status_val, progress, budget
                )

            # Actualizar el proyecto
            updated_project = ProjectCRUD.update_project_orm(db, project_id, **kwargs)

            db.commit()

            if updated_project is None:
                raise HTTPException(status_code=404, detail="Project not found")

            updated_project["is_owner"] = access["is_owner"]

            return updated_project

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al actualizar el proyecto: {str(e)}",
            )

    @staticmethod
    def delete_project(db, project_id: str, user_id: str):
        """
        Elimina un proyecto con validaciones

        Args:
            db: Conexión a la base de datos
            project_id: ID del proyecto
            user_id: ID del usuario solicitante

        Raises:
            HTTPException si no tiene permisos o hay miembros
        """
        try:
            # Verificar que el proyecto existe
            project = ProjectCRUD.get_project_by_id_orm(db, project_id)

            if not project:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado"
                )

            # Solo el owner puede eliminar
            if str(project["owner_id"]) != str(user_id):
                raise HTTPException(
                    status_code=http_status.HTTP_403_FORBIDDEN,
                    detail="Solo el propietario puede eliminar el proyecto",
                )

            # Eliminar miembros en cascada antes de borrar el proyecto
            members = ProjectCRUD.get_project_members_orm(db, project_id)
            for member in members:
                ProjectCRUD.remove_project_member_orm(db, project_id, member["user_id"])

            # Eliminar el proyecto (soft delete)
            # ORM cascade relationships automatically handle deletion of tables, columns, and mappings
            success = ProjectCRUD.delete_project_orm(db, project_id)

            if not success:
                raise HTTPException(
                    status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error al eliminar el proyecto",
                )

            db.commit()

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al eliminar el proyecto: {str(e)}",
            )

    @staticmethod
    def get_project_members(db, project_id: str, user_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene los miembros de un proyecto

        Args:
            db: Conexión a la base de datos
            project_id: ID del proyecto
            user_id: ID del usuario solicitante

        Returns:
            Lista de miembros

        Raises:
            HTTPException si no tiene permisos
        """
        # Verificar que el proyecto existe
        project = ProjectCRUD.get_project_by_id_orm(db, project_id)

        if not project:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado"
            )

        # Solo el owner puede ver los miembros
        if str(project["owner_id"]) != str(user_id):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Solo el propietario puede ver los miembros",
            )

        return ProjectCRUD.get_project_members_orm(db, project_id)

    @staticmethod
    def remove_member(db, project_id: str, member_user_id: str, user_id: str):
        """
        Elimina un miembro de un proyecto

        Args:
            db: Conexión a la base de datos
            project_id: ID del proyecto
            member_user_id: ID del usuario a eliminar
            user_id: ID del usuario solicitante

        Raises:
            HTTPException si no tiene permisos
        """
        try:
            # Verificar que el proyecto existe
            project = ProjectCRUD.get_project_by_id_orm(db, project_id)

            if not project:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado"
                )

            # Solo el owner puede eliminar miembros
            if str(project["owner_id"]) != str(user_id):
                raise HTTPException(
                    status_code=http_status.HTTP_403_FORBIDDEN,
                    detail="Solo el propietario puede eliminar miembros",
                )

            # Eliminar el miembro
            success = ProjectCRUD.remove_project_member_orm(db, project_id, member_user_id)

            if not success:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail="El miembro no existe en este proyecto",
                )

            db.commit()

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al eliminar el miembro: {str(e)}",
            )

    @staticmethod
    def leave_project(db, project_id: str, user_id: str):
        """
        Permite a un miembro salir de un proyecto

        Args:
            db: Conexión a la base de datos
            project_id: ID del proyecto
            user_id: ID del usuario solicitante

        Raises:
            HTTPException si es owner o no es miembro
        """
        try:
            # Verificar que el proyecto existe
            project = ProjectCRUD.get_project_by_id_orm(db, project_id)

            if not project:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado"
                )

            # El owner no puede salir
            if str(project["owner_id"]) == str(user_id):
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="Eres el propietario: no puedes salir del proyecto",
                )

            # Verificar que es miembro
            access = ProjectCRUD.check_user_access_orm(db, project_id, user_id)

            if not access or access["is_owner"]:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="No perteneces a este proyecto",
                )

            # Eliminar la membresía
            ProjectCRUD.remove_project_member_orm(db, project_id, user_id)

            db.commit()

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al salir del proyecto: {str(e)}",
            )

    @staticmethod
    def get_user_stats(db, user_id: str, comparison_days: int = 30) -> Dict[str, Any]:
        """
        Obtiene estadísticas del usuario con comparación histórica

        Args:
            db: Conexión a la base de datos
            user_id: ID del usuario
            comparison_days: Días hacia atrás para comparar

        Returns:
            Dict con estadísticas y cambios porcentuales
        """
        try:
            # Obtener métricas comparadas
            metrics = ProjectCRUD.get_user_metrics_comparison_orm(db, user_id, comparison_days)

            if not metrics["current"]:
                # Si no hay métricas, forzar recálculo
                ProjectCRUD.force_recalculate_user_metrics_orm(db, user_id)
                metrics = ProjectCRUD.get_user_metrics_comparison_orm(db, user_id, comparison_days)

            current = metrics["current"]
            previous = metrics["previous"]

            # Función auxiliar para calcular cambio porcentual
            def calculate_change(current_val, previous_val):
                if previous_val == 0:
                    return 100.0 if current_val > 0 else 0.0
                return round(((current_val - previous_val) / previous_val) * 100, 1)

            # Construir respuesta con estadísticas
            stats = {
                "total_projects": {
                    "value": current["total_projects"],
                    "change": calculate_change(
                        current["total_projects"], previous["total_projects"]
                    ),
                    "positive": current["total_projects"] >= previous["total_projects"],
                },
                "active_projects": {
                    "value": current["active_projects"],
                    "change": calculate_change(
                        current["active_projects"], previous["active_projects"]
                    ),
                    "positive": current["active_projects"] >= previous["active_projects"],
                },
                "completed_projects": {
                    "value": current["completed_projects"],
                    "change": calculate_change(
                        current["completed_projects"], previous["completed_projects"]
                    ),
                    "positive": current["completed_projects"] >= previous["completed_projects"],
                },
                "total_budget": {
                    "value": float(current["total_budget"]),
                    "change": calculate_change(
                        float(current["total_budget"]), float(previous["total_budget"])
                    ),
                    "positive": current["total_budget"] >= previous["total_budget"],
                },
                "avg_progress": {
                    "value": float(current["avg_progress"]),
                    "change": calculate_change(
                        float(current["avg_progress"]), float(previous["avg_progress"])
                    ),
                    "positive": current["avg_progress"] >= previous["avg_progress"],
                },
            }

            return stats

        except Exception as e:
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al obtener estadísticas: {str(e)}",
            )

    # app/services/project_service.py

    @staticmethod
    def update_project_last_accessed(db, project_id: str, user_id: str) -> None:
        """Actualiza last_accessed_at del proyecto (silencioso si no tiene acceso)."""
        ProjectCRUD.update_project_last_accessed_orm(db, project_id, user_id)

    @staticmethod
    def get_recent_projects(db, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Obtiene proyectos recientes del usuario ordenados por last_accessed_at DESC."""
        try:
            return ProjectCRUD.get_recent_projects_for_user_orm(db, user_id, limit)
        except Exception as e:
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al obtener proyectos recientes: {str(e)}",
            )

    @staticmethod
    def get_metrics_history(db, user_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Obtiene el historial de métricas para gráficos
        Versión simplificada que devuelve array vacío si no hay datos
        """
        try:
            metrics = ProjectCRUD.get_user_metrics_history_orm(db, user_id, days)
            # Si no hay métricas históricas, devolver array vacío
            return metrics if metrics else []
        except Exception as e:
            # En lugar de error, devolver array vacío
            print(f"Warning: No se pudieron obtener métricas históricas: {str(e)}")
            return []

    @staticmethod
    def add_member(db, project_id: str, owner_user_id: str, identifier: str, role: str = "viewer"):
        """
        Añade un miembro a un proyecto

        Args:
            db: Conexión a la base de datos
            project_id: ID del proyecto
            owner_user_id: ID del propietario (quien añade)
            identifier: Email o username del usuario a añadir
            role: Rol del miembro (viewer o editor)
        """
        try:
            # Verificar que el proyecto existe
            project = ProjectCRUD.get_project_by_id_orm(db, project_id)

            if not project:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado"
                )

            # Solo el owner puede añadir miembros
            if str(project["owner_id"]) != str(owner_user_id):
                raise HTTPException(
                    status_code=http_status.HTTP_403_FORBIDDEN,
                    detail="Solo el propietario puede añadir miembros",
                )

            # Buscar usuario por email o username (ORM version)
            user = user_crud.get_user_by_email_orm(db, identifier)
            if not user:
                user = user_crud.get_user_by_username_orm(db, identifier)

            if not user:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado"
                )

            user_id = user["id"]

            # No se puede añadir al propietario
            if str(user_id) == str(owner_user_id):
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="No puedes añadirte a ti mismo como miembro",
                )

            # Verificar si ya es miembro (mantener comportamiento original)
            existing = (
                db.query(ProjectMember)
                .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
                .first()
            )

            if existing:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="El usuario ya es miembro del proyecto",
                )

            # Añadir miembro (ORM version)
            ProjectCRUD.add_project_member_orm(
                db=db, project_id=project_id, user_id=user_id, role=role, added_by=owner_user_id
            )

            db.commit()

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al añadir miembro: {str(e)}",
            )

    @staticmethod
    def update_member_role(
        db, project_id: str, member_user_id: str, new_role: str, owner_user_id: str
    ):
        """
        Actualiza el rol de un miembro

        Args:
            db: Conexión a la base de datos
            project_id: ID del proyecto
            member_user_id: ID del usuario miembro
            new_role: Nuevo rol
            owner_user_id: ID del propietario
        """
        try:
            # Verificar que el proyecto existe
            project = ProjectCRUD.get_project_by_id_orm(db, project_id)

            if not project:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado"
                )

            # Solo el owner puede actualizar roles
            if str(project["owner_id"]) != str(owner_user_id):
                raise HTTPException(
                    status_code=http_status.HTTP_403_FORBIDDEN,
                    detail="Solo el propietario puede actualizar roles",
                )

            # Actualizar rol (ORM version)
            success = ProjectCRUD.update_member_role_orm(
                db=db, project_id=project_id, user_id=member_user_id, new_role=new_role
            )

            if not success:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail="El miembro no existe en este proyecto",
                )

            db.commit()

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al actualizar rol: {str(e)}",
            )
