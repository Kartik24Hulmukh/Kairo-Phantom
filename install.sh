#!/usr/bin/env bash
# Kairo Phantom — Honest Install Script
#
# This script installs Kairo Phantom's Python dependencies and verifies
# the installation by running a smoke test. It is honest about what
# platform it works on:
#
#   - Linux (Ubuntu/Debian): FULLY SUPPORTED (CI-verified)
#   - macOS: PARTIAL (Python tests pass, Rust platform code compiles, live ghost-typing NOT verified)
#   - Windows: PARTIAL (Python tests pass with COM stubs, live ghost-typing needs real Windows)
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/Kartik24Hulmukh/Kairo-Phantom/master/install.sh | bash
#   OR: bash install.sh

set -euo pipefail

echo "👻 Kairo Phantom — Installer"
echo ""

# Detect platform
OS="$(uname -s)"
case "$OS" in
    Linux*)  PLATFORM="Linux";;
    Darwin*) PLATFORM="macOS";;
    MINGW*|MSYS*|CYGWIN*) PLATFORM="Windows";;
    *) PLATFORM="Unknown";;
esac

echo "Detected platform: $PLATFORM"
echo ""

if [ "$PLATFORM" = "Unknown" ]; then
    echo "❌ Unsupported platform: $OS"
    echo "   Kairo Phantom requires Linux, macOS, or Windows."
    exit 1
fi

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 is not installed."
    echo "   Install Python 3.12+ from https://python.org"
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python version: $PY_VERSION"

if [ "$PY_VERSION" \< "3.11" ]; then
    echo "❌ Python 3.11+ required, found $PY_VERSION"
    exit 1
fi

echo ""

# Clone if not already in the repo
if [ ! -f "kairo-sidecar/requirements.txt" ]; then
    echo "📦 Cloning Kairo Phantom..."
    git clone https://github.com/Kartik24Hulmukh/Kairo-Phantom.git kairo-phantom
    cd kairo-phantom
else
    echo "📦 Already in Kairo Phantom directory"
fi

echo ""

# Create virtual environment
echo "🔧 Creating virtual environment..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "📥 Installing dependencies..."
pip install --upgrade pip -q
pip install -r kairo-sidecar/requirements.txt -q 2>&1 | tail -3
pip install -r requirements-test.txt -q 2>&1 | tail -3
pip install pytest pytest-asyncio pytest-xdist pytest-timeout anyio -q 2>&1 | tail -3

echo ""

# Smoke test
echo "🧪 Running smoke test..."
KAIRO_OFFLINE=1 KAIRO_FORCE_CPU=1 KAIRO_SEALED=1 python -c "
import kernel
import packs
import bench
print('kernel + packs + bench import OK')
" 2>&1

if [ $? -ne 0 ]; then
    echo "❌ Smoke test failed. Please check the error above."
    exit 1
fi

echo ""

# Run a quick test
echo "🔬 Running corpus integrity test..."
KAIRO_OFFLINE=1 KAIRO_FORCE_CPU=1 KAIRO_SEALED=1 python -m pytest tests/test_corpus_integrity.py -v --timeout=30 -p no:cacheprovider 2>&1 | tail -10

echo ""

# Platform-specific notes
if [ "$PLATFORM" = "Linux" ]; then
    echo "✅ Linux: Full Python test suite CI-verified."
    echo "   Rust platform code (AT-SPI2) compiles and is tested on Ubuntu."
    echo "   Live ghost-typing requires a desktop environment (X11/Wayland)."
elif [ "$PLATFORM" = "macOS" ]; then
    echo "⚠️  macOS: Python tests pass. Rust platform code (AXUIElement) compiles."
    echo "   Live ghost-typing is NOT CI-verified (no macOS CI runner)."
    echo "   See CROSS_PLATFORM_REPORT.md for self-certified test results."
elif [ "$PLATFORM" = "Windows" ]; then
    echo "⚠️  Windows: Python tests pass with COM stubs."
    echo "   Live ghost-typing (Win32 UIAutomation) needs real Windows hardware."
    echo "   Rust platform code compiles on Windows (CI-verified on windows-latest)."
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "  make build     — Verify kernel + packs + bench import"
echo "  make test      — Run the test suite"
echo "  make demo      — Run the legal-redline demo"
echo "  make bench     — Run benchmarks"
echo ""
echo "Docs: https://github.com/Kartik24Hulmukh/Kairo-Phantom"
