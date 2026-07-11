# Scripts de PowerShell para Windows

Estos scripts son equivalentes a los comandos del `Makefile` pero para Windows.

## 🚀 Uso

### Instalación inicial
```powershell
.\scripts\install.ps1
```

### Ejecutar tests
```powershell
.\scripts\test.ps1
```

### Verificar linting
```powershell
.\scripts\lint.ps1
```

### Formatear código automáticamente
```powershell
.\scripts\format.ps1
```

### Limpiar artefactos
```powershell
.\scripts\clean.ps1
```

## 🔧 Configuración Inicial

### 1. Permitir ejecución de scripts (solo primera vez)

En PowerShell como Administrador:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 2. Instalar dependencias globales

```powershell
# Python tools
pip install pre-commit flake8 black isort mypy

# Instalar dependencias del proyecto
.\scripts\install.ps1
```

## 💡 Tips

- Puedes crear aliases en tu perfil de PowerShell:
  ```powershell
  # Abrir perfil
  notepad $PROFILE

  # Añadir aliases
  function dev-install { .\scripts\install.ps1 }
  function dev-test { .\scripts\test.ps1 }
  function dev-lint { .\scripts\lint.ps1 }
  function dev-format { .\scripts\format.ps1 }
  function dev-clean { .\scripts\clean.ps1 }
  ```

- Después de guardar y recargar PowerShell, podrás usar:
  ```powershell
  dev-install
  dev-test
  dev-lint
  ```
