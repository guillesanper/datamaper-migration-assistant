# Script de limpieza para Windows
Write-Host "🧹 Limpiando artefactos..." -ForegroundColor Cyan

# Python cache
Write-Host "`n🐍 Limpiando cache de Python..." -ForegroundColor Yellow
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path . -Recurse -Directory -Filter ".pytest_cache" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path . -Recurse -Directory -Filter "*.egg-info" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path . -Recurse -File -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue

# Coverage reports
Write-Host "📊 Limpiando reportes de coverage..." -ForegroundColor Yellow
Remove-Item -Path "backend\.coverage" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "backend\htmlcov" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "backend\coverage.xml" -Force -ErrorAction SilentlyContinue

# Build artifacts
Write-Host "🏗️  Limpiando builds..." -ForegroundColor Yellow
Remove-Item -Path "frontend\dist" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "landing\dist" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "`n✅ ¡Limpieza completada!" -ForegroundColor Green
