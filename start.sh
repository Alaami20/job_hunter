#!/bin/bash
# ─────────────────────────────────────────────
#  Alaa's Job Hunter — One-Click Starter (Mac)
#  Double-click this file OR run: bash start.sh
# ─────────────────────────────────────────────

echo ""
echo "🚀 Alaa's Job Hunter — Growwithyouu"
echo "────────────────────────────────────"

# Check Python
if ! command -v python3 &> /dev/null; then
  echo "❌ Python not found. Install from https://python.org"
  read -p "Press Enter to exit..."
  exit 1
fi

# Install packages
echo "📦 Installing packages..."
pip install python-jobspy anthropic gspread google-auth flask --quiet

# Check if API key is set
if grep -q "YOUR_ANTHROPIC_API_KEY_HERE" job_scraper.py; then
  echo ""
  echo "⚠️  STOP — You need to add your Anthropic API key first!"
  echo "   1. Open job_scraper.py in any text editor"
  echo "   2. Find line: ANTHROPIC_API_KEY = \"YOUR_ANTHROPIC_API_KEY_HERE\""
  echo "   3. Replace with your real key from console.anthropic.com"
  echo ""
  read -p "Press Enter after you've added the key, then run this script again..."
  exit 1
fi

# Check if google_creds.json exists
if [ ! -f "google_creds.json" ]; then
  echo ""
  echo "⚠️  STOP — google_creds.json is missing!"
  echo "   Follow SETUP.md Step 3 to create it."
  echo ""
  read -p "Press Enter to exit..."
  exit 1
fi

echo ""
echo "Which mode do you want?"
echo "  1) Scrape jobs → save to Google Sheets (job_scraper.py)"
echo "  2) Open web dashboard (web_app.py)"
echo ""
read -p "Enter 1 or 2: " choice

if [ "$choice" = "1" ]; then
  echo ""
  echo "🔍 Starting job scan..."
  python3 job_scraper.py
elif [ "$choice" = "2" ]; then
  echo ""
  echo "🌐 Starting web dashboard..."
  echo "   Open your browser at: http://localhost:5000"
  echo ""
  python3 web_app.py
else
  echo "Invalid choice. Run the script again."
fi

read -p "Press Enter to exit..."
