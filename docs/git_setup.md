# Git Setup Guide

## Initial Setup

1. Install Git:
   ```bash
   # Windows: Download from https://git-scm.com/download/win
   # Linux:
   sudo apt-get install git  # Ubuntu/Debian
   sudo dnf install git      # Fedora
   ```

2. Configure Git:
   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "your.email@example.com"
   ```

## Project Setup

1. Create a new repository on GitHub:
   - Go to https://github.com
   - Click "New repository"
   - Name it "flight-controls" or similar
   - Don't initialize with README (we'll add our own)

2. Initialize local repository:
   ```bash
   # Navigate to your project directory
   cd path/to/flight-controls

   # Initialize git
   git init

   # Add the remote repository
   git remote add origin https://github.com/YOUR_USERNAME/flight-controls.git
   ```

3. Create .gitignore file:
   ```bash
   # Create .gitignore file
   touch .gitignore
   ```

```text:.gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
venv/
ENV/

# IDE
.idea/
.vscode/
*.swp
*.swo

# Project specific
settings/
*.log
*.json
!flight_controls_settings.json

# Operating System
.DS_Store
Thumbs.db
```

4. Add and commit files:
   ```bash
   # Add all files
   git add .

   # Make initial commit
   git commit -m "Initial commit"

   # Push to GitHub
   git push -u origin main
   ```

## Project Structure

Your repository should look like this: 