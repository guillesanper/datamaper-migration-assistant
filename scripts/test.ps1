# Script de tests para Windows
Write-Host "🧪 Ejecutando tests..." -ForegroundColor Cyan

Write-Host "`n📝 Tests del backend..." -ForegroundColor Yellow
Set-Location backend
pytest -v
$backendResult = $LASTEXITCODE
Set-Location ..

Write-Host "`n⚠️  Frontend no tiene tests configurados aún" -ForegroundColor Yellow

if ($backendResult -eq 0) {
    Write-Host "`n✅ Todos los tests pasaron!" -ForegroundColor Green
} else {
    Write-Host "`n❌ Algunos tests fallaron" -ForegroundColor Red
    exit 1
}
