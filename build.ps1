# Build Script for Manatoki Crawler
Write-Host "Starting Build Process..." -ForegroundColor Green

# 1. Install Dependencies
Write-Host "Installing/Updating Dependencies..." -ForegroundColor Cyan
pip install -r requirements.txt

# 2. Run PyInstaller
Write-Host "Building Executable..." -ForegroundColor Cyan
# --onefile: Create a single executable
# --name: Name of the output file
# --paths src: Add src directory to PYTHONPATH so imports work
# --clean: Clean PyInstaller cache
# --noconfirm: Do not ask for confirmation to overwrite output directory
pyinstaller --noconfirm --onefile --clean --name "ManatokiDownloader" --paths src src/main.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build Success!" -ForegroundColor Green
    Write-Host "Executable can be found in ./dist/ManatokiDownloader.exe" -ForegroundColor Yellow
} else {
    Write-Host "Build Failed!" -ForegroundColor Red
    exit 1
}
