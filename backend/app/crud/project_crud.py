# app/crud/project_crud.py
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class ProjectCRUD:
    """
    Clase para manejar operaciones CRUD de proyectos en la base de datos
    Separa la lógica de acceso a datos de la lógica de negocio
    """

    # ========================================================================
    # SQLALCHEMY ORM VERSIONS - Funciones con sufijo _orm
    # ========================================================================

    @staticmethod
    def create_project_orm(
        db,
        owner_id: str,
        name: str,
        description: str,
        origin_db: str,
        destination_db: str,
        status: str = "active",
        progress: int = 0,
        budget: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Crea un nuevo proyecto en la base de datos (ORM version)

        Args:
            db: SQLAlchemy Session
            owner_id: ID del propietario del proyecto
            name: Nombre del proyecto
            description: Descripción del proyecto
            origin_db: Base de datos de origen
            destination_db: Base de datos de destino
            status: Estado del proyecto (active, paused, completed)
            progress: Progreso del proyecto (0-100)
            budget: Presupuesto del proyecto

        Returns:
            Dict con los datos del proyecto creado
        """
        from app.models.orm import Project
        from app.utils.orm_helpers import model_to_dict

        current_time = datetime.now(timezone.utc).replace(tzinfo=None)

        new_project = Project(
            id=uuid.uuid4(),
            name=name,
            description=description,
            origin_db=origin_db,
            destination_db=destination_db,
            owner_id=owner_id,
            status=status,
            progress=progress,
            budget=budget,
            is_deleted=False,
            created_at=current_time,
            updated_at=current_time,
        )

        db.add(new_project)
        db.commit()
        db.refresh(new_project)

        return model_to_dict(new_project)  # type: ignore[return-value]

    @staticmethod
    def get_project_by_id_orm(db, project_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un proyecto por su ID (ORM version)

        Args:
            db: SQLAlchemy Session
            project_id: ID del proyecto

        Returns:
            Dict con los datos del proyecto o None si no existe
        """
        from app.models.orm import Project
        from app.utils.orm_helpers import model_to_dict

        project = (
            db.query(Project).filter(Project.id == project_id, Project.is_deleted == False).first()
        )

        return model_to_dict(project) if project else None

    @staticmethod
    def get_user_projects_orm(
        db,
        user_id: str,
        status: Optional[str] = None,
        sort_by: str = "name",
        sort_order: str = "asc",
    ) -> List[Dict[str, Any]]:
        """
        Obtiene todos los proyectos de un usuario (propios + donde es miembro) (ORM version)

        Args:
            db: SQLAlchemy Session
            user_id: ID del usuario
            status: Filtro opcional por estado
            sort_by: Campo por el cual ordenar
            sort_order: Orden de ordenamiento (asc o desc)

        Returns:
            Lista de proyectos
        """
        from sqlalchemy import case, exists, select

        from app.models.orm import Project, ProjectMember

        # Validar campos de ordenamiento permitidos
        allowed_sort_fields = ["name", "status", "progress", "budget", "updated_at", "created_at"]
        if sort_by not in allowed_sort_fields:
            sort_by = "name"

        # Construir query base
        query = db.query(
            Project, case((Project.owner_id == user_id, True), else_=False).label("is_owner")
        ).filter(
            (Project.owner_id == user_id)
            | exists(
                select(1).where(
                    (ProjectMember.project_id == Project.id) & (ProjectMember.user_id == user_id)
                )
            ),
            Project.is_deleted == False,
        )

        # Aplicar filtro de status si se proporciona
        if status:
            query = query.filter(Project.status == status)

        # Aplicar ordenamiento
        sort_column = getattr(Project, sort_by)
        if sort_order.lower() == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        results = query.all()

        # Convertir a lista de dicts
        projects = []
        for project, is_owner in results:
            from app.utils.orm_helpers import model_to_dict

            project_dict = model_to_dict(project)
            if project_dict is not None:
                project_dict["is_owner"] = is_owner
                projects.append(project_dict)

        return projects

    @staticmethod
    def update_project_orm(db, project_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Actualiza un proyecto existente (ORM version)

        Args:
            db: SQLAlchemy Session
            project_id: ID del proyecto
            **kwargs: Campos a actualizar

        Returns:
            Dict con los datos del proyecto actualizado o None
        """
        from app.models.orm import Project
        from app.utils.orm_helpers import model_to_dict

        # Campos permitidos para actualizar
        allowed_fields = [
            "name",
            "description",
            "origin_db",
            "destination_db",
            "status",
            "progress",
            "budget",
        ]

        # Filtrar solo los campos permitidos que se pasaron
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

        if not updates:
            # Si no hay campos para actualizar, solo devolver el proyecto actual
            return ProjectCRUD.get_project_by_id_orm(db, project_id)

        # Agregar updated_at
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        updates["updated_at"] = current_time

        # Actualizar usando update()
        result = (
            db.query(Project)
            .filter(Project.id == project_id, Project.is_deleted == False)
            .update(updates, synchronize_session="fetch")
        )

        db.commit()

        if result == 0:
            return None

        # Obtener el proyecto actualizado
        project = db.query(Project).filter(Project.id == project_id).first()
        return model_to_dict(project) if project else None

    @staticmethod
    def delete_project_orm(db, project_id: str) -> bool:
        """
        Elimina un proyecto (soft delete) (ORM version)

        Args:
            db: SQLAlchemy Session
            project_id: ID del proyecto

        Returns:
            True si se eliminó correctamente, False si no
        """
        from app.models.orm import Project

        current_time = datetime.now(timezone.utc).replace(tzinfo=None)

        result = (
            db.query(Project)
            .filter(Project.id == project_id, Project.is_deleted == False)
            .update({"is_deleted": True, "updated_at": current_time}, synchronize_session="fetch")
        )

        db.commit()

        return bool(result > 0)

    @staticmethod
    def count_user_projects_orm(db, user_id: str) -> int:
        """
        Cuenta el número de proyectos propios de un usuario (ORM version)

        Args:
            db: SQLAlchemy Session
            user_id: ID del usuario

        Returns:
            Número de proyectos
        """
        from app.models.orm import Project

        count = (
            db.query(Project)
            .filter(Project.owner_id == user_id, Project.is_deleted == False)
            .count()
        )

        return int(count)

    @staticmethod
    def get_project_members_orm(db, project_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene los miembros de un proyecto (ORM version)

        Args:
            db: SQLAlchemy Session
            project_id: ID del proyecto

        Returns:
            Lista de miembros con sus datos
        """
        from app.models.orm import ProjectMember, User

        results = (
            db.query(ProjectMember.user_id, ProjectMember.role, User.email, User.username)
            .join(User, ProjectMember.user_id == User.id)
            .filter(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.created_at.asc())
            .all()
        )

        return [
            {
                "user_id": str(user_id),
                "role": role.value if hasattr(role, "value") else role,  # Handle enum
                "email": email,
                "username": username,
            }
            for user_id, role, email, username in results
        ]

    @staticmethod
    def remove_project_member_orm(db, project_id: str, user_id: str) -> bool:
        """
        Elimina un miembro de un proyecto (ORM version)

        Args:
            db: SQLAlchemy Session
            project_id: ID del proyecto
            user_id: ID del usuario a eliminar

        Returns:
            True si se eliminó correctamente, False si no
        """
        from app.models.orm import ProjectMember

        result = (
            db.query(ProjectMember)
            .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
            .delete()
        )

        db.commit()

        return bool(result > 0)

    @staticmethod
    def check_user_access_orm(db, project_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Verifica si un usuario tiene acceso a un proyecto y con qué rol (ORM version)

        Args:
            db: SQLAlchemy Session
            project_id: ID del proyecto
            user_id: ID del usuario

        Returns:
            Dict con información de acceso: {is_owner: bool, role: str|None}
        """
        from app.models.orm import Project, ProjectMember

        # Verificar si el proyecto existe y si es owner
        project = (
            db.query(Project).filter(Project.id == project_id, Project.is_deleted == False).first()
        )

        if not project:
            return None

        if str(project.owner_id) == str(user_id):
            return {"is_owner": True, "role": None}

        # Verificar si es miembro
        member = (
            db.query(ProjectMember)
            .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
            .first()
        )

        if member:
            role_value = member.role.value if hasattr(member.role, "value") else member.role
            return {"is_owner": False, "role": role_value}

        return None

    @staticmethod
    def add_project_member_orm(
        db, project_id: str, user_id: str, role: str = "viewer", added_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Añade un miembro a un proyecto o actualiza su rol si ya existe (ORM version)

        Args:
            db: SQLAlchemy session
            project_id: ID del proyecto
            user_id: ID del usuario a añadir
            role: Rol del usuario (owner, editor, viewer)
            added_by: ID del usuario que invitó (opcional)

        Returns:
            Dict con los datos del membership creado/actualizado

        Raises:
            HTTPException 404: Si proyecto no existe
            HTTPException 400: Si rol inválido
        """
        import uuid
        from datetime import datetime, timezone

        from fastapi import HTTPException, status

        from app.models.orm.project import MemberRole, Project, ProjectMember
        from app.utils.orm_helpers import model_to_dict

        # Validar rol
        valid_roles = ["owner", "editor", "viewer"]
        if role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rol inválido. Debe ser uno de: {', '.join(valid_roles)}",
            )

        # Verificar que proyecto existe
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado"
            )

        # Buscar membership existente
        existing = (
            db.query(ProjectMember)
            .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
            .first()
        )

        if existing:
            # Actualizar rol existente
            existing.role = MemberRole[role.upper()]
            db.commit()
            db.refresh(existing)
            return model_to_dict(existing)  # type: ignore[return-value]
        else:
            # Crear nuevo membership
            new_member = ProjectMember(
                id=uuid.uuid4(),
                project_id=uuid.UUID(project_id),
                user_id=uuid.UUID(user_id),
                role=MemberRole[role.upper()],
                added_by=uuid.UUID(added_by) if added_by else None,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.add(new_member)
            db.commit()
            db.refresh(new_member)
            return model_to_dict(new_member)  # type: ignore[return-value]

    @staticmethod
    def update_member_role_orm(db, project_id: str, user_id: str, new_role: str) -> bool:
        """
        Actualiza el rol de un miembro existente (ORM version)

        Args:
            db: SQLAlchemy Session
            project_id: ID del proyecto
            user_id: ID del usuario miembro
            new_role: Nuevo rol (owner, editor, viewer)

        Returns:
            True si se actualizó exitosamente, False si el miembro no existe

        Raises:
            HTTPException 400: Si rol inválido
        """
        from fastapi import HTTPException, status

        from app.models.orm.project import MemberRole, ProjectMember

        # Validar rol
        valid_roles = ["owner", "editor", "viewer"]
        if new_role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rol inválido. Debe ser uno de: {', '.join(valid_roles)}",
            )

        # Buscar miembro
        member = (
            db.query(ProjectMember)
            .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
            .first()
        )

        if not member:
            return False

        # Actualizar rol
        member.role = MemberRole[new_role.upper()]
        db.commit()
        db.refresh(member)

        return True

    @staticmethod
    def get_user_metrics_comparison_orm(db, user_id: str, days_back: int = 30) -> Dict[str, Any]:
        """
        Obtiene métricas actuales y las compara con métricas anteriores (ORM version)

        Args:
            db: SQLAlchemy Session
            user_id: ID del usuario
            days_back: Días hacia atrás para comparar (por defecto 30)

        Returns:
            Dict con métricas actuales y cambios porcentuales
        """
        from datetime import date, timedelta

        from sqlalchemy import func, text

        from app.models.orm import ProjectMetricsHistory

        # Obtener métricas de hoy
        current_metrics = (
            db.query(ProjectMetricsHistory)
            .filter(
                ProjectMetricsHistory.user_id == user_id,
                ProjectMetricsHistory.date == func.current_date(),
            )
            .first()
        )

        # Si no hay métricas de hoy, calcularlas usando la función de PostgreSQL
        if not current_metrics:
            db.execute(
                text("SELECT calculate_and_save_user_metrics(:user_id)"), {"user_id": user_id}
            )
            db.commit()

            current_metrics = (
                db.query(ProjectMetricsHistory)
                .filter(
                    ProjectMetricsHistory.user_id == user_id,
                    ProjectMetricsHistory.date == func.current_date(),
                )
                .first()
            )

        # Obtener métricas de hace X días
        target_date = date.today() - timedelta(days=days_back)
        previous_metrics = (
            db.query(ProjectMetricsHistory)
            .filter(
                ProjectMetricsHistory.user_id == user_id, ProjectMetricsHistory.date == target_date
            )
            .order_by(ProjectMetricsHistory.date.desc())
            .first()
        )

        # Si no hay métricas previas, usar ceros
        previous_dict: Dict[str, Any]
        if not previous_metrics:
            previous_dict = {
                "total_projects": 0,
                "active_projects": 0,
                "paused_projects": 0,
                "completed_projects": 0,
                "total_budget": 0,
                "avg_progress": 0,
            }
        else:
            from app.utils.orm_helpers import model_to_dict

            previous_dict = model_to_dict(previous_metrics)  # type: ignore[assignment]

        from app.utils.orm_helpers import model_to_dict

        current_dict = model_to_dict(current_metrics) if current_metrics else None

        return {"current": current_dict, "previous": previous_dict}

    @staticmethod
    def get_user_metrics_history_orm(db, user_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Obtiene el historial de métricas de un usuario (ORM version)

        Args:
            db: SQLAlchemy Session
            user_id: ID del usuario
            days: Número de días de historial

        Returns:
            Lista de métricas ordenadas por fecha descendente
        """
        from datetime import date, timedelta

        from app.models.orm import ProjectMetricsHistory

        target_date = date.today() - timedelta(days=days)

        metrics = (
            db.query(ProjectMetricsHistory)
            .filter(
                ProjectMetricsHistory.user_id == user_id, ProjectMetricsHistory.date >= target_date
            )
            .order_by(ProjectMetricsHistory.date.desc())
            .all()
        )

        from app.utils.orm_helpers import models_to_dict_list

        return models_to_dict_list(metrics)

    @staticmethod
    def force_recalculate_user_metrics_orm(db, user_id: str):
        """
        Fuerza el recálculo de las métricas de un usuario para hoy (ORM version)

        Args:
            db: SQLAlchemy Session
            user_id: ID del usuario
        """
        from sqlalchemy import text

        db.execute(text("SELECT calculate_and_save_user_metrics(:user_id)"), {"user_id": user_id})
        db.commit()

    @staticmethod
    def update_project_last_accessed_orm(db, project_id: str, user_id: str) -> None:
        """
        Actualiza last_accessed_at del proyecto si el usuario es owner o miembro.
        Silencioso (no raise) si no tiene acceso o el proyecto no existe.

        Args:
            db: SQLAlchemy Session
            project_id: ID del proyecto
            user_id: ID del usuario
        """
        from sqlalchemy import exists, select

        from app.models.orm import Project, ProjectMember

        has_access = (
            db.query(Project.id)
            .filter(
                Project.id == project_id,
                Project.is_deleted == False,
                (Project.owner_id == user_id)
                | exists(
                    select(1).where(
                        (ProjectMember.project_id == Project.id)
                        & (ProjectMember.user_id == user_id)
                    )
                ),
            )
            .first()
        )

        if not has_access:
            return

        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        db.query(Project).filter(Project.id == project_id).update(
            {"last_accessed_at": current_time}, synchronize_session="fetch"
        )
        db.commit()

    @staticmethod
    def get_recent_projects_for_user_orm(
        db, user_id: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Devuelve proyectos donde el usuario es owner o miembro,
        ordenados por last_accessed_at DESC (NULLs al final), limitados a `limit`.

        Args:
            db: SQLAlchemy Session
            user_id: ID del usuario
            limit: Número máximo de proyectos a devolver

        Returns:
            Lista de proyectos ordenados por acceso reciente
        """
        from sqlalchemy import case, exists, select

        from app.models.orm import Project, ProjectMember

        results = (
            db.query(
                Project,
                case((Project.owner_id == user_id, True), else_=False).label("is_owner"),
            )
            .filter(
                (Project.owner_id == user_id)
                | exists(
                    select(1).where(
                        (ProjectMember.project_id == Project.id)
                        & (ProjectMember.user_id == user_id)
                    )
                ),
                Project.is_deleted == False,
            )
            .order_by(Project.last_accessed_at.desc().nulls_last())
            .limit(limit)
            .all()
        )

        projects = []
        for project, is_owner in results:
            from app.utils.orm_helpers import model_to_dict

            project_dict = model_to_dict(project)
            if project_dict is not None:
                project_dict["is_owner"] = is_owner
                projects.append(project_dict)

        return projects
