from typing import Any, Dict


class ErrorCode:
    # Auth / Session
    NOT_AUTHENTICATED = "auth.not_authenticated"
    SESSION_INVALID = "auth.session_invalid"
    SESSION_EXPIRED = "auth.session_expired"
    SESSION_REVOKED = "auth.session_revoked"
    INVALID_USER = "auth.invalid_user"
    GET_USER_FAILED = "auth.get_user_failed"

    # Projects
    PROJECT_NOT_FOUND = "project.not_found"
    PROJECT_FORBIDDEN = "project.forbidden"
    PROJECT_NO_ACCESS = "project.no_access"
    PROJECT_EMAIL_REQUIRED = "project.member_email_required"
    PROJECT_INVALID_ROLE = "project.invalid_role"
    PROJECT_STATS_ERROR = "project.stats_error"

    # DB / Schemas
    TABLE_NOT_FOUND = "db.table_not_found"
    COLUMN_NOT_FOUND = "db.column_not_found"
    COLUMN_LIMIT = "schema.column_limit"  # params: max, plan

    # Mappings
    FILENAME_REQUIRED = "mapping.filename_required"
    UNSUPPORTED_FORMAT = "mapping.unsupported_format"

    # Mappings — importación de estructura (JSON no cumple el esquema)
    IMPORT_MISSING_FIELD = "mapping.import_missing_field"  # params: field, where
    IMPORT_UNKNOWN_FIELD = "mapping.import_unknown_field"  # params: field, where
    IMPORT_INVALID_VALUE = "mapping.import_invalid_value"  # params: field, where, value, allowed
    IMPORT_SCHEMA_INVALID = "mapping.import_schema_invalid"  # params: where, reason

    # Billing
    BILLING_NOT_OWNER = "billing.not_owner"
    BILLING_INVALID_EMAIL = "billing.invalid_email"
    BILLING_MISSING_SIG = "billing.missing_signature"

    # Rate Limiting
    RATE_LIMIT_BLOCKED = "rate_limit.blocked"  # params: seconds
    RATE_LIMIT_EXCEEDED = "rate_limit.exceeded"

    # Security
    CSRF_TOKEN_INVALID = "security.csrf_token_invalid"

    # Notifications
    NOTIFICATION_NOT_FOUND = "notification.not_found"

    # User Settings
    USER_NOT_FOUND = "user.not_found"
    USER_UPDATE_FAILED = "user.update_failed"
    USER_WRONG_PASSWORD = "user.wrong_password"
    USER_IMAGE_FORMAT = "user.image_format"
    USER_IMAGE_SIZE = "user.image_size"
    USER_IMAGE_PROCESS = "user.image_process"
    USER_PASSWORD_MISMATCH = "user.password_mismatch"
    USER_2FA_NOT_SETUP = "user.2fa_not_setup"
    USER_2FA_INVALID_CODE = "user.2fa_invalid_code"
    USER_2FA_NOT_ACTIVE = "user.2fa_not_active"
    USER_2FA_INVALID_STATE = "user.2fa_invalid_state"
    USER_SESSION_NOT_FOUND = "user.session_not_found"
    USER_API_KEY_INVALID = "user.api_key_invalid"
    USER_API_KEY_NOT_FOUND = "user.api_key_not_found"

    # Schema — Validación
    TABLE_NAME_REQUIRED = "schema.table_name_required"
    TABLE_NAME_INVALID = "schema.table_name_invalid"
    TABLE_TYPE_REQUIRED = "schema.table_type_required"
    TABLE_TYPE_INVALID = "schema.table_type_invalid"
    COLUMN_NAME_REQUIRED = "schema.column_name_required"
    COLUMN_NAME_INVALID = "schema.column_name_invalid"
    DATA_TYPE_REQUIRED = "schema.data_type_required"
    DATA_TYPE_INVALID = "schema.data_type_invalid"
    DATA_TYPE_FORMAT_INVALID = "schema.data_type_format_invalid"  # params: type
    LENGTH_INVALID = "schema.length_invalid"  # params: type, min, max
    PRECISION_INVALID = "schema.precision_invalid"  # params: type, min, max
    SCALE_INVALID = "schema.scale_invalid"  # params: type, precision

    # Schema — Lógica de negocio
    TABLE_DUPLICATE = "schema.table_duplicate"  # params: type, name
    COLUMN_DUPLICATE = "schema.column_duplicate"  # params: name
    TABLE_LIMIT = "schema.table_limit"  # params: max, plan
    SCHEMA_NO_PERMISSION = "schema.no_permission"
    SCHEMA_OPERATION_FAILED = "schema.operation_failed"

    # Mapping
    MAPPING_NOT_FOUND = "mapping.not_found"

    # Version control
    VERSION_NOT_FOUND = "version.not_found"
    TAG_NOT_FOUND = "version.tag_not_found"
    VERSION_OPERATION_FAILED = "version.operation_failed"

    # Admin
    ADMIN_ACCESS_REQUIRED = "admin.access_required"

    # Billing (adicional)
    BILLING_WEBHOOK_ERROR = "billing.webhook_error"

    # Servidor genérico
    INTERNAL_ERROR = "server.internal_error"


def make_error(code: str, **params: Any) -> Dict[str, Any]:
    return {"code": code, "params": params} if params else {"code": code}
