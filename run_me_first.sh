#!/bin/bash
# ╔══════════════════════════════════════════╗
# ║  Alaa's Job Hunter — Quick Start Script  ║
# ║  Double-click this file to set up!       ║
# ╚══════════════════════════════════════════╝

echo ""
echo "======================================"
echo "  Alaa's AI Job Hunter - Growwithyouu"
echo "======================================"
echo ""

# Go to the script's own directory
cd "$(dirname "$0")"

echo "Installing Python packages..."
pip install -r requirements.txt

echo ""
echo "======================================"
echo "  Setup complete!"
echo ""
echo "  NEXT STEPS:"
echo "  1. Open job_scraper.py and add your"
echo "     Anthropic API key (line 24)"
echo ""
echo "  2. Add google_creds.json to this folder"
echo "     (see SETUP_GUIDE.md for how)"
echo ""
echo "  3. Run:  python job_scraper.py"
echo "  4. Then: python web_app.py"
echo "     Open: http://localhost:5000"
echo "======================================"
echo ""
read -p "Press Enter to close..."
