#!/bin/bash

# GitHub Repository Setup Script
# This script helps you set up the Website Intelligence Platform repository on GitHub

set -e

echo "================================================"
echo "Website Intelligence Platform - GitHub Setup"
echo "================================================"
echo ""

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check for GitHub CLI
if command_exists gh; then
    echo "✅ GitHub CLI found"
    USE_GH_CLI=true
else
    echo "⚠️  GitHub CLI not found. Please install it for automatic setup:"
    echo "   https://cli.github.com/"
    echo ""
    echo "Or follow manual setup instructions in SETUP_GITHUB.md"
    USE_GH_CLI=false
fi

# Get GitHub username
read -p "Enter your GitHub username: " GITHUB_USERNAME

# Get repository visibility preference
echo "Repository visibility:"
echo "1) Public"
echo "2) Private"
read -p "Choose (1 or 2): " VISIBILITY_CHOICE

if [ "$VISIBILITY_CHOICE" = "2" ]; then
    VISIBILITY="--private"
    VISIBILITY_TEXT="private"
else
    VISIBILITY="--public"
    VISIBILITY_TEXT="public"
fi

# Repository name
REPO_NAME="website-intelligence-platform"

if [ "$USE_GH_CLI" = true ]; then
    echo ""
    echo "Creating $VISIBILITY_TEXT repository: $GITHUB_USERNAME/$REPO_NAME"

    # Create repository using GitHub CLI
    gh repo create "$REPO_NAME" \
        $VISIBILITY \
        --description "AI-powered website navigation intelligence extraction platform" \
        --homepage "https://github.com/$GITHUB_USERNAME/$REPO_NAME" \
        --clone=false \
        --add-readme=false

    echo "✅ Repository created successfully!"

    # Set up remote
    git remote add origin "https://github.com/$GITHUB_USERNAME/$REPO_NAME.git" 2>/dev/null || \
    git remote set-url origin "https://github.com/$GITHUB_USERNAME/$REPO_NAME.git"

    # Rename branch to main
    git branch -M main

    echo ""
    read -p "Do you want to push code to GitHub now? (y/n): " PUSH_CHOICE
    if [ "$PUSH_CHOICE" = "y" ] || [ "$PUSH_CHOICE" = "Y" ]; then
        echo "Pushing code to GitHub..."
        git push -u origin main
        echo "✅ Code pushed successfully!"
    fi

    echo ""
    echo "Setting up GitHub repository settings..."

    # Enable issues
    gh repo edit --enable-issues --enable-wiki

    # Create labels for issues
    echo "Creating issue labels..."
    gh label create "enhancement" --description "New feature or request" --color "a2eeef" 2>/dev/null || true
    gh label create "bug" --description "Something isn't working" --color "d73a4a" 2>/dev/null || true
    gh label create "documentation" --description "Improvements or additions to documentation" --color "0075ca" 2>/dev/null || true
    gh label create "ci/cd" --description "Continuous Integration/Deployment" --color "000000" 2>/dev/null || true
    gh label create "crawler" --description "Web crawler related" --color "1d76db" 2>/dev/null || true
    gh label create "ai/llm" --description "AI/LLM related" --color "ff9900" 2>/dev/null || true

    echo ""
    echo "Would you like to set up GitHub Secrets now?"
    echo "You'll need:"
    echo "  - API keys (OpenAI, Anthropic)"
    echo "  - AWS credentials (optional)"
    echo "  - Docker Hub credentials (optional)"
    read -p "Continue with secrets setup? (y/n): " SECRETS_CHOICE

    if [ "$SECRETS_CHOICE" = "y" ] || [ "$SECRETS_CHOICE" = "Y" ]; then
        echo ""
        echo "Setting up GitHub Secrets..."
        echo "(Press Enter to skip any secret you don't have)"

        # OpenAI API Key
        read -sp "Enter OPENAI_API_KEY: " OPENAI_API_KEY
        echo ""
        if [ ! -z "$OPENAI_API_KEY" ]; then
            gh secret set OPENAI_API_KEY --body "$OPENAI_API_KEY"
            echo "✅ OPENAI_API_KEY set"
        fi

        # Anthropic API Key
        read -sp "Enter ANTHROPIC_API_KEY: " ANTHROPIC_API_KEY
        echo ""
        if [ ! -z "$ANTHROPIC_API_KEY" ]; then
            gh secret set ANTHROPIC_API_KEY --body "$ANTHROPIC_API_KEY"
            echo "✅ ANTHROPIC_API_KEY set"
        fi

        # AWS Credentials
        read -sp "Enter AWS_ACCESS_KEY_ID (optional): " AWS_ACCESS_KEY_ID
        echo ""
        if [ ! -z "$AWS_ACCESS_KEY_ID" ]; then
            gh secret set AWS_ACCESS_KEY_ID --body "$AWS_ACCESS_KEY_ID"
            echo "✅ AWS_ACCESS_KEY_ID set"

            read -sp "Enter AWS_SECRET_ACCESS_KEY: " AWS_SECRET_ACCESS_KEY
            echo ""
            if [ ! -z "$AWS_SECRET_ACCESS_KEY" ]; then
                gh secret set AWS_SECRET_ACCESS_KEY --body "$AWS_SECRET_ACCESS_KEY"
                echo "✅ AWS_SECRET_ACCESS_KEY set"
            fi
        fi

        # Docker Hub Credentials
        read -p "Enter DOCKER_USERNAME (optional): " DOCKER_USERNAME
        if [ ! -z "$DOCKER_USERNAME" ]; then
            gh secret set DOCKER_USERNAME --body "$DOCKER_USERNAME"
            echo "✅ DOCKER_USERNAME set"

            read -sp "Enter DOCKER_PASSWORD: " DOCKER_PASSWORD
            echo ""
            if [ ! -z "$DOCKER_PASSWORD" ]; then
                gh secret set DOCKER_PASSWORD --body "$DOCKER_PASSWORD"
                echo "✅ DOCKER_PASSWORD set"
            fi
        fi

        echo ""
        echo "✅ Secrets configuration complete!"
    fi

else
    echo ""
    echo "Manual Setup Required"
    echo "===================="
    echo ""
    echo "1. Create repository on GitHub:"
    echo "   https://github.com/new"
    echo ""
    echo "   Repository name: $REPO_NAME"
    echo "   Description: AI-powered website navigation intelligence extraction platform"
    echo "   Visibility: $VISIBILITY_TEXT"
    echo ""
    echo "2. After creating, run these commands:"
    echo ""
    echo "   git remote add origin https://github.com/$GITHUB_USERNAME/$REPO_NAME.git"
    echo "   git branch -M main"
    echo "   git push -u origin main"
    echo ""
    echo "3. Follow the instructions in SETUP_GITHUB.md for:"
    echo "   - Setting up secrets"
    echo "   - Configuring environments"
    echo "   - Enabling GitHub Actions"
fi

echo ""
echo "================================================"
echo "Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Review and complete any manual steps in SETUP_GITHUB.md"
echo "2. Install pre-commit hooks locally:"
echo "   source .venv/bin/activate"
echo "   uv pip install pre-commit"
echo "   pre-commit install"
echo ""
echo "3. Your repository URL:"
echo "   https://github.com/$GITHUB_USERNAME/$REPO_NAME"
echo ""
echo "4. Check GitHub Actions:"
echo "   https://github.com/$GITHUB_USERNAME/$REPO_NAME/actions"
echo ""
echo "Happy coding! 🚀"