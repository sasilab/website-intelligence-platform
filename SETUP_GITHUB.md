# GitHub Repository Setup Instructions

## Creating the Repository

### Option 1: Using GitHub CLI (Recommended)
If you have GitHub CLI installed, run:
```bash
gh repo create website-intelligence-platform --public --description "AI-powered website navigation intelligence extraction platform" --clone=false
git remote add origin https://github.com/YOUR_USERNAME/website-intelligence-platform.git
git branch -M main
git push -u origin main
```

### Option 2: Using GitHub Web Interface
1. Go to [GitHub](https://github.com/new)
2. Create a new repository with:
   - Name: `website-intelligence-platform`
   - Description: `AI-powered website navigation intelligence extraction platform`
   - Visibility: Public (or Private if preferred)
   - DO NOT initialize with README, gitignore, or license (we already have them)

3. After creating, run these commands in your terminal:
```bash
cd website-intelligence-platform
git remote add origin https://github.com/YOUR_USERNAME/website-intelligence-platform.git
git branch -M main
git push -u origin main
```

## Setting up GitHub Secrets

After creating the repository, add these secrets in Settings → Secrets and variables → Actions:

### Required Secrets:
- `OPENAI_API_KEY`: Your OpenAI API key
- `ANTHROPIC_API_KEY`: Your Anthropic API key
- `AWS_ACCESS_KEY_ID`: AWS access key (for deployments)
- `AWS_SECRET_ACCESS_KEY`: AWS secret key
- `DOCKER_USERNAME`: Docker Hub username
- `DOCKER_PASSWORD`: Docker Hub password
- `PYPI_TOKEN`: PyPI token for package publishing
- `SLACK_WEBHOOK`: Slack webhook URL for notifications
- `API_URL`: Production API URL
- `API_KEY`: API key for scheduled tasks
- `STAGING_API_KEY`: Staging environment API key
- `PRODUCTION_API_KEY`: Production environment API key

### Optional Secrets:
- `CLIENT_LIST`: JSON array of client IDs for scheduled crawls
- `EMAIL_USERNAME`: Email username for reports
- `EMAIL_PASSWORD`: Email password for reports

## Enabling GitHub Actions

1. Go to Settings → Actions → General
2. Under "Workflow permissions", select:
   - "Read and write permissions"
   - "Allow GitHub Actions to create and approve pull requests"

## Setting up Environments

1. Go to Settings → Environments
2. Create two environments:
   - `staging`
   - `production`

3. For `production` environment:
   - Add protection rules
   - Required reviewers: 1
   - Deployment branches: Only `main` branch

## Installing Pre-commit Hooks Locally

After cloning the repository:
```bash
# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install pre-commit
uv pip install pre-commit

# Install the git hook scripts
pre-commit install

# Run against all files (optional)
pre-commit run --all-files
```

## First Deployment

After pushing to GitHub:

1. The CI pipeline will run automatically
2. To deploy to staging:
   - Push to `main` branch or
   - Manually trigger the CD workflow

3. To deploy to production:
   - Create a git tag: `git tag v1.0.0`
   - Push the tag: `git push origin v1.0.0`
   - Or manually trigger the CD workflow

## Verifying Setup

1. Check Actions tab for workflow runs
2. Monitor the CI pipeline on pull requests
3. Check Insights → Dependency graph for security updates
4. Enable Dependabot in Settings → Security

## Webhook Integration

To enable automatic crawls on deployment:

1. In your deployment environment, set up the webhook endpoint
2. In GitHub, go to Settings → Webhooks
3. Add webhook:
   - Payload URL: `https://your-api.com/api/webhooks/deployment`
   - Content type: `application/json`
   - Secret: Generate a secure secret
   - Events: Select "Deployments" and "Deploy keys"

## Branch Protection

1. Go to Settings → Branches
2. Add branch protection rule for `main`:
   - Require pull request reviews
   - Require status checks to pass
   - Require branches to be up to date
   - Include administrators
   - Restrict who can push to matching branches

## Success Checklist

- [ ] Repository created on GitHub
- [ ] Code pushed to main branch
- [ ] Secrets configured
- [ ] GitHub Actions enabled
- [ ] Environments set up
- [ ] Pre-commit hooks installed locally
- [ ] First CI run successful
- [ ] Branch protection configured
- [ ] Webhook integration (optional)
- [ ] Dependabot enabled (optional)