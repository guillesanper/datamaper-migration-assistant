# Script de linting para Windows
Write-Host "🔍 Ejecutando linters..." -ForegroundColor Cyan

$errors = 0

# Backend
Write-Host "`n🐍 Linting backend..." -ForegroundColor Yellow
Set-Location backend

Write-Host "  - flake8..." -ForegroundColor Gray
flake8 .
if ($LASTEXITCODE -ne 0) { $errors++ }

Write-Host "  - black..." -ForegroundColor Gray
black --check .
if ($LASTEXITCODE -ne 0) { $errors++ }

Write-Host "  - isort..." -ForegroundColor Gray
isort --check-only .
if ($LASTEXITCODE -ne 0) { $errors++ }

Write-Host "  - mypy..." -ForegroundColor Gray
mypy app --ignore-missing-imports
if ($LASTEXITCODE -ne 0) { $errors++ }

Set-Location ..

# Frontend
Write-Host "`n⚛️  Linting frontend..." -ForegroundColor Yellow
Set-Location frontend

Write-Host "  - ESLint..." -ForegroundColor Gray
npm run lint
if ($LASTEXITCODE -ne 0) { $errors++ }

Write-Host "  - TypeScript..." -ForegroundColor Gray
npx tsc -b --noEmit
if ($LASTEXITCODE -ne 0) { $errors++ }

Set-Location ..

# Resultado
if ($errors -eq 0) {
    Write-Host "`n✅ Todos los linters pasaron!" -ForegroundColor Green
} else {
    Write-Host "`n❌ $errors linter(s) fallaron" -ForegroundColor Red
    Write-Host "💡 Ejecuta: .\scripts\format.ps1 para arreglar automáticamente" -ForegroundColor Yellow
    exit 1
}
