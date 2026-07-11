# Script de formateo para Windows
Write-Host "🎨 Formateando código..." -ForegroundColor Cyan

# Backend
Write-Host "`n🐍 Formateando backend..." -ForegroundColor Yellow
Set-Location backend

Write-Host "  - black..." -ForegroundColor Gray
black .

Write-Host "  - isort..." -ForegroundColor Gray
isort .

Set-Location ..

# Frontend
Write-Host "`n⚛️  Formateando frontend..." -ForegroundColor Yellow
Set-Location frontend

Write-Host "  - ESLint (auto-fix)..." -ForegroundColor Gray
npm run lint -- --fix

Set-Location ..

Write-Host "`n✅ Formateo completado!" -ForegroundColor Green
