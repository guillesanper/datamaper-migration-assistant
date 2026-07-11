# backend/migrations/rollback.py
"""
Sistema de rollback para migraciones.
Permite revertir cambios de migraciones de forma segura.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from validators import BackupManager

# ============================================================================
# ROLLBACK MANAGER CLASS
# ============================================================================


class RollbackManager:
    """Gestor de rollbacks de migraciones"""

    def __init__(self, db_connection, checkpoints_file: str = None):
        """
        Inicializar gestor de rollbacks

        Args:
            db_connection: Conexión a la base de datos
            checkpoints_file: Ruta al archivo de checkpoints (default: migration_checkpoints.json)
        """
        self.db = db_connection
        self.backup_manager = BackupManager(db_connection)

        if checkpoints_file is None:
            # Default to .claude/claudeChangeControl/Migration Type Refactor/migration_checkpoints.json
            project_root = Path(__file__).parent.parent.parent
            self.checkpoints_file = (
                project_root
                / ".claude"
                / "claudeChangeControl"
                / "Migration Type Refactor"
                / "migration_checkpoints.json"
            )
        else:
            self.checkpoints_file = Path(checkpoints_file)

    def load_checkpoints(self) -> Dict[str, Any]:
        """Cargar archivo de checkpoints"""
        if not self.checkpoints_file.exists():
            return {"rollback_points": [], "phases": {}}

        with open(self.checkpoints_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_checkpoints(self, data: Dict[str, Any]) -> None:
        """Guardar archivo de checkpoints"""
        with open(self.checkpoints_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def list_rollback_points(self) -> List[Dict[str, Any]]:
        """Listar todos los puntos de rollback disponibles"""
        checkpoints = self.load_checkpoints()
        return checkpoints.get("rollback_points", [])

    def create_rollback_point(
        self,
        checkpoint_id: str,
        phase: str,
        description: str,
        backup_files: List[str] = None,
        git_commit: str = None,
    ) -> Dict[str, Any]:
        """
        Crear un nuevo punto de rollback

        Args:
            checkpoint_id: ID único del checkpoint
            phase: Fase de migración (ej: "2.1")
            description: Descripción del checkpoint
            backup_files: Lista de archivos de backup
            git_commit: Hash del commit de git (opcional)

        Returns:
            Información del checkpoint creado
        """
        checkpoints = self.load_checkpoints()

        rollback_point = {
            "checkpoint_id": checkpoint_id,
            "phase": phase,
            "timestamp": datetime.now().isoformat(),
            "description": description,
            "backup_files": backup_files or [],
            "git_commit": git_commit,
            "can_rollback": True,
        }

        if "rollback_points" not in checkpoints:
            checkpoints["rollback_points"] = []

        checkpoints["rollback_points"].append(rollback_point)

        self.save_checkpoints(checkpoints)

        return rollback_point

    def get_rollback_point(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Obtener información de un checkpoint específico"""
        rollback_points = self.list_rollback_points()

        for point in rollback_points:
            if point["checkpoint_id"] == checkpoint_id:
                return point

        return None

    def execute_rollback(self, checkpoint_id: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        Ejecutar rollback a un checkpoint específico

        Args:
            checkpoint_id: ID del checkpoint
            dry_run: Si es True, solo muestra qué haría sin ejecutar

        Returns:
            Resultado del rollback
        """
        # Get checkpoint info
        checkpoint = self.get_rollback_point(checkpoint_id)

        if not checkpoint:
            return {"success": False, "message": f"Checkpoint {checkpoint_id} no encontrado"}

        if not checkpoint.get("can_rollback", False):
            return {"success": False, "message": f"Checkpoint {checkpoint_id} no permite rollback"}

        result = {
            "success": True,
            "checkpoint": checkpoint,
            "actions_taken": [],
            "dry_run": dry_run,
        }

        # Step 1: Restore database from backups
        if checkpoint.get("backup_files"):
            for backup_file in checkpoint["backup_files"]:
                if dry_run:
                    result["actions_taken"].append(
                        {"action": "restore_backup", "file": backup_file, "status": "would_execute"}
                    )
                else:
                    # Extract backup_id from filename
                    backup_id = Path(backup_file).stem.split("_metadata")[0]

                    restore_result = self.backup_manager.restore_backup(backup_id)

                    result["actions_taken"].append(
                        {
                            "action": "restore_backup",
                            "backup_id": backup_id,
                            "status": "success" if restore_result["success"] else "failed",
                            "details": restore_result,
                        }
                    )

        # Step 2: Revert git if commit hash is provided
        if checkpoint.get("git_commit"):
            if dry_run:
                result["actions_taken"].append(
                    {
                        "action": "git_revert",
                        "commit": checkpoint["git_commit"],
                        "status": "would_execute",
                    }
                )
            else:
                # NOTE: In a real implementation, you would execute git commands here
                # For now, we just log the action
                result["actions_taken"].append(
                    {
                        "action": "git_revert",
                        "commit": checkpoint["git_commit"],
                        "status": "manual_required",
                        "message": f"Execute manually: git revert {checkpoint['git_commit']}",
                    }
                )

        # Step 3: Update checkpoints file to mark current phase
        if not dry_run:
            checkpoints = self.load_checkpoints()

            # Update current_phase to the checkpoint's phase
            checkpoints["current_phase"] = checkpoint["phase"]
            checkpoints["status"] = "rolled_back"

            self.save_checkpoints(checkpoints)

            result["actions_taken"].append({"action": "update_checkpoints", "status": "success"})

        # Step 4: Validation
        if not dry_run:
            validation_result = self._validate_rollback(checkpoint)
            result["validation"] = validation_result

        return result

    def _validate_rollback(self, checkpoint: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validar que el rollback se ejecutó correctamente

        Args:
            checkpoint: Información del checkpoint

        Returns:
            Resultado de la validación
        """
        cursor = self.db.cursor(cursor_factory=RealDictCursor)

        try:
            # Check database integrity
            cursor.execute("SELECT COUNT(*) as count FROM tables")
            tables_count = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM columns")
            columns_count = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM mappings")
            mappings_count = cursor.fetchone()["count"]

            return {
                "success": True,
                "message": "Validación completada",
                "database_state": {
                    "tables": tables_count,
                    "columns": columns_count,
                    "mappings": mappings_count,
                },
            }

        except Exception as e:
            return {"success": False, "message": f"Error en validación: {str(e)}"}
        finally:
            cursor.close()


# ============================================================================
# CLI INTERFACE
# ============================================================================


def main():
    """CLI para gestión de rollbacks"""
    parser = argparse.ArgumentParser(description="Sistema de rollback para migraciones")

    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    # List command
    list_parser = subparsers.add_parser("list", help="Listar puntos de rollback")

    # Rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Ejecutar rollback")
    rollback_parser.add_argument("checkpoint_id", help="ID del checkpoint")
    rollback_parser.add_argument(
        "--dry-run", action="store_true", help="Modo preview (no ejecuta cambios)"
    )

    # Create command
    create_parser = subparsers.add_parser("create", help="Crear punto de rollback")
    create_parser.add_argument("checkpoint_id", help="ID del checkpoint")
    create_parser.add_argument("--phase", required=True, help="Fase de migración")
    create_parser.add_argument("--description", required=True, help="Descripción")
    create_parser.add_argument("--git-commit", help="Hash del commit de git")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    # Connect to database
    # NOTE: In a real implementation, you would load connection params from config
    try:
        db = psycopg2.connect(
            host="localhost", database="relan_db", user="postgres", password="your_password"
        )
    except Exception as e:
        print(f"Error conectando a la base de datos: {e}")
        print("Por favor, configurar las credenciales de la base de datos.")
        return

    manager = RollbackManager(db)

    # Execute command
    if args.command == "list":
        rollback_points = manager.list_rollback_points()

        if not rollback_points:
            print("No hay puntos de rollback disponibles.")
            return

        print("\n=== Puntos de Rollback Disponibles ===\n")

        for point in rollback_points:
            print(f"ID: {point['checkpoint_id']}")
            print(f"Fase: {point['phase']}")
            print(f"Fecha: {point['timestamp']}")
            print(f"Descripción: {point['description']}")
            print(f"Puede revertir: {'Sí' if point.get('can_rollback') else 'No'}")

            if point.get("backup_files"):
                print(f"Backups: {len(point['backup_files'])} archivos")

            if point.get("git_commit"):
                print(f"Git commit: {point['git_commit']}")

            print("-" * 50)

    elif args.command == "rollback":
        result = manager.execute_rollback(args.checkpoint_id, dry_run=args.dry_run)

        if args.dry_run:
            print("\n=== MODO DRY-RUN (Preview) ===\n")

        print(f"\nRollback a checkpoint: {args.checkpoint_id}")
        print(f"Estado: {'Éxito' if result['success'] else 'Falló'}")

        if not result["success"]:
            print(f"Error: {result['message']}")
            return

        print(f"\nAcciones {'que se ejecutarían' if args.dry_run else 'ejecutadas'}:")

        for action in result["actions_taken"]:
            action_type = action["action"]
            status = action["status"]
            print(f"  - {action_type}: {status}")

            if "message" in action:
                print(f"    {action['message']}")

        if not args.dry_run and "validation" in result:
            validation = result["validation"]
            print(f"\nValidación: {'Éxito' if validation['success'] else 'Falló'}")

            if "database_state" in validation:
                state = validation["database_state"]
                print(f"  Tablas: {state['tables']}")
                print(f"  Columnas: {state['columns']}")
                print(f"  Mappings: {state['mappings']}")

    elif args.command == "create":
        result = manager.create_rollback_point(
            checkpoint_id=args.checkpoint_id,
            phase=args.phase,
            description=args.description,
            git_commit=args.git_commit,
        )

        print(f"\nPunto de rollback creado: {result['checkpoint_id']}")
        print(f"Fase: {result['phase']}")
        print(f"Timestamp: {result['timestamp']}")

    db.close()


if __name__ == "__main__":
    main()
