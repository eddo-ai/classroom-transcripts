# Classroom Transcripts

Azure Functions app for transcribing classroom audio using AssemblyAI, with a focus on speaker identification and classroom discussion analysis.

## Project Version

The current project version is **0.1.0**.

## Project Structure

```
classroom-transcripts/
├── src/
│   └── functions/              # Azure Functions code
│       ├── core/              # Core business logic
│       ├── utils/             # Utility functions
│       ├── examples/          # Example implementations
│       ├── tests/            # Function-specific tests
│       ├── SubmitTranscription/ # Function trigger
│       ├── function_app.py   # Main function app
│       ├── transcription_function.py # Transcription logic
│       └── requirements.txt  # Function dependencies
├── tests/
│   ├── unit/               # Unit tests
│   ├── integration/        # Integration tests
│   ├── e2e/               # End-to-end tests
│   └── data/              # Test data
│       ├── audio/         # Test audio files
│       └── fixtures/      # Test fixtures
├── docs/                  # Documentation
├── environments/          # Environment configurations
├── scripts/              # Utility scripts
└── streamlit/           # Streamlit web interface
```

## Features

- **Audio Transcription**: Automatically transcribe classroom audio files using AssemblyAI
- **Speaker Identification**: Distinguish between teacher and student voices
- **Azure Integration**: Seamless integration with Azure Blob Storage and Functions
- **Local Development**: Full local development support with Azurite
- **Comprehensive Testing**: Unit, integration, and end-to-end tests
- **Web Interface**: Streamlit-based interface for transcript analysis

## Prerequisites

- Python 3.12+
- Docker (for Azurite)
- Azure CLI
- 1Password CLI (for secrets management)
- Node.js 18+ (for Azure Functions Core Tools)

## Setup

1. **Clone the Repository**:

   ```bash
   git clone https://github.com/yourusername/classroom-transcripts.git
   cd classroom-transcripts
   ```

2. **Install Dependencies**:

   ```bash
   # Install uv if not already installed
   pip install uv

   # Install project dependencies using uv
   uv pip install -e .

   # Install function dependencies and generate requirements.txt
   cd src/functions
   uv pip install -e .
   uv pip compile pyproject.toml -o requirements.txt

   # Install Azure Functions Core Tools
   npm i -g azure-functions-core-tools@4 --unsafe-perm true
   ```

   > Note: The `requirements.txt` file in the functions directory is auto-generated from `pyproject.toml`.
   > Do not edit it directly - modify dependencies in `pyproject.toml` instead.

3. **Start Local Storage**:

   ```bash
   # Start Azurite in Docker
   docker run -d -p 10000:10000 -p 10001:10001 -p 10002:10002 \
     mcr.microsoft.com/azure-storage/azurite
   ```

4. **Configure Environment**:
   ```bash
   # Generate local environment file from 1Password
   op inject --in-file .env.onepassword --out-file .env.local
   ```

## Development

1. **Run Tests**:

   ```bash
   # Run all tests
   pytest

   # Run specific test suites
   pytest tests/unit/
   pytest tests/integration/
   pytest tests/e2e/
   ```

2. **Start Function App**:

   ```bash
   cd src/functions
   func start
   ```

3. **Start Web Interface**:
   ```bash
   cd streamlit
   streamlit run app.py
   ```

## Deployment

1. **Create Azure Resources**:

   ```bash
   # Create resource group
   az group create --name classroom-transcripts-rg --location eastus

   # Create storage account
   az storage account create \
     --name classroomtranscripts \
     --resource-group classroom-transcripts-rg \
     --sku Standard_LRS

   # Create function app
   az functionapp create \
     --name classroom-transcripts-func \
     --resource-group classroom-transcripts-rg \
     --storage-account classroomtranscripts \
     --runtime python \
     --runtime-version 3.12 \
     --functions-version 4 \
     --os-type linux
   ```

2. **Configure GitHub Actions**:
   Required secrets:

   - `AZURE_FUNCTIONAPP_PUBLISH_PROFILE`
   - `ASSEMBLYAI_API_KEY`
   - `AZURE_STORAGE_CONNECTION_STRING`
   - `AZURE_FUNCTION_KEY`

3. **Deploy**:
   - Push to main branch, or
   - Manually trigger the deployment workflow

## Monitoring

1. **View Function Logs**:

   ```bash
   az monitor app-insights query \
     --app classroom-transcripts-func \
     --analytics-query "traces | where timestamp > ago(5m) and severityLevel >= 2 | project timestamp, message, severityLevel" \
     --resource-group classroom-transcripts-rg
   ```

2. **Check Function Status**:
   ```bash
   az functionapp show \
     --name classroom-transcripts-func \
     --resource-group classroom-transcripts-rg
   ```

## Environment Variables

| Variable                | Description                | Required | Default        |
| ----------------------- | -------------------------- | -------- | -------------- |
| `ASSEMBLYAI_API_KEY`    | AssemblyAI API key         | Yes      | -              |
| `AZURE_STORAGE_ACCOUNT` | Azure Storage account name | Yes      | -              |
| `AZURE_FUNCTION_KEY`    | Function app key           | Yes      | -              |
| `WEBSITE_HOSTNAME`      | Function app hostname      | No       | localhost:7071 |
| `MGMT_API_ACCESS_TOKEN` | Management API access token| Yes      | -              |

See `.env.example` for a complete list of configuration options.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

# Classroom Transcript Web App

## Overview

This is a web app that supports teachers and curriculum coaches in analyzing classroom transcripts.

## Features

- Teachers can upload audio files and analyze them with a focus on the teacher's voice, the student's voice, and the overall classroom discussion.
- Uploaded audio files are transcribed and published to a Google Drive folder.
- Coaches and admins can see all transcripts.
- List and detail views show the name and email of the uploading user.

## Automate Azure Resource Creation

1. **Create Azure Resources using Azure CLI**:

   ```bash
   # Create resource group
   az group create --name classroom-transcripts-rg --location eastus

   # Create storage account
   az storage account create \
     --name classroomtranscripts \
     --resource-group classroom-transcripts-rg \
     --sku Standard_LRS

   # Create function app
   az functionapp create \
     --name classroom-transcripts-func \
     --resource-group classroom-transcripts-rg \
     --storage-account classroomtranscripts \
     --runtime python \
     --runtime-version 3.12 \
     --functions-version 4 \
     --os-type linux
   ```

2. **Define Environment Variables in a `.env` file**:

   Create a `.env` file in the root directory and add the following environment variables:

   ```bash
   # AssemblyAI Configuration
   ASSEMBLYAI_API_KEY="your_assemblyai_api_key"
   ASSEMBLYAI_CALLBACK_URL="your_callback_url"

   # Azure Identity Configuration
   AZURE_TENANT_ID="your_azure_tenant_id"
   AZURE_CLIENT_ID="your_azure_client_id"
   AZURE_CLIENT_SECRET="your_azure_client_secret"
   AZURE_SUBSCRIPTION_ID="your_azure_subscription_id"

   # Azure Storage Account
   AZURE_STORAGE_ACCOUNT="your_storage_account_name"

   # Azure Storage Connection String
   AZURE_STORAGE_CONNECTION_STRING="your_storage_connection_string"

   # Google OAuth Configuration
   GOOGLE_CLIENT_ID="your_oauth_client_id"
   GOOGLE_CLIENT_SECRET="your_oauth_client_secret"
   GOOGLE_REDIRECT_URI="your_redirect_uri"

   # Debug Configuration
   DEBUG=false

   # Client Configuration
   ORGANIZATION_NAME="your_organization_name"
   FEEDBACK_EMAIL="your_feedback_email"

   # Management API Access Token
   MGMT_API_ACCESS_TOKEN="your_management_api_access_token"
   ```

3. **Use GitHub Actions for Deployment**:

   Configure GitHub Actions to automate the deployment process. Add the following workflow files to the `.github/workflows` directory:

   - **deploy.yml**:

     ```yaml
     name: Deploy to Azure Functions

     on:
       push:
         branches: [main]
       workflow_dispatch:

     env:
       AZURE_FUNCTIONAPP_NAME: classroom-transcripts-func
       AZURE_FUNCTIONAPP_PACKAGE_PATH: '.'
       PYTHON_VERSION: '3.11'

     jobs:
       build-and-deploy:
         runs-on: ubuntu-latest
         steps:
           - name: Checkout repository
             uses: actions/checkout@v4

           - name: Setup Python
             uses: actions/setup-python@v5
             with:
               python-version: ${{ env.PYTHON_VERSION }}
               cache: 'pip'

           - name: Install dependencies
             run: |
               python -m pip install --upgrade pip
               pip install -r requirements.txt
               pip install -r src/functions/requirements.txt

           - name: Run Tests
             env:
               AZURE_STORAGE_ACCOUNT: devstoreaccount1
               AZURE_STORAGE_CONNECTION_STRING: ${{ secrets.AZURE_STORAGE_CONNECTION_STRING }}
               ASSEMBLYAI_API_KEY: ${{ secrets.ASSEMBLYAI_API_KEY }}
               AZURE_FUNCTION_KEY: ${{ secrets.AZURE_FUNCTION_KEY }}
             run: |
               pip install pytest pytest-azurepipelines
               pytest tests/ -v -m "not integration"

           - name: Build package
             run: |
               mkdir -p ./package
               cp -r src/functions/* ./package/
               cp requirements.txt ./package/
               cd package
               zip -r ../function.zip .

           - name: Deploy to Azure Functions
             uses: Azure/functions-action@v1
             with:
               app-name: ${{ env.AZURE_FUNCTIONAPP_NAME }}
               package: function.zip
               publish-profile: ${{ secrets.AZURE_FUNCTIONAPP_PUBLISH_PROFILE }}
     ```

   - **classroom-transcripts-AutoDeployTrigger-7f3cca96-827b-4384-b81f-b951ea9eb8c0.yml**:

     ```yaml
     name: Trigger auto deployment for classroom-transcripts

     # When this action will be executed
     on:
       # Automatically trigger it when detected changes in repo
       push:
         branches: [main]
         paths:
           - '**'
           - '.github/workflows/classroom-transcripts-AutoDeployTrigger-7f3cca96-827b-4384-b81f-b951ea9eb8c0.yml'

       # Allow manual trigger
       workflow_dispatch:

     jobs:
       build-and-deploy:
         runs-on: ubuntu-latest
         permissions:
           id-token: write #This is required for requesting the OIDC JWT Token
           contents: read #Required when GH token is used to authenticate with private repo

         steps:
           - name: Checkout to the branch
             uses: actions/checkout@v2

           - name: Set up Python 3.13
             uses: actions/setup-python@v4
             with:
               python-version: '3.13'

           - name: Azure Login
             uses: azure/login@v1
             with:
               client-id: ${{ secrets.CLASSROOMTRANSCRIPTS_AZURE_CLIENT_ID }}
               tenant-id: ${{ secrets.CLASSROOMTRANSCRIPTS_AZURE_TENANT_ID }}
               subscription-id: ${{ secrets.CLASSROOMTRANSCRIPTS_AZURE_SUBSCRIPTION_ID }}

           - name: Build and push container image to registry
             uses: azure/container-apps-deploy-action@v2
             with:
               appSourcePath: ${{ github.workspace }}
               dockerfilePath: ./Dockerfile
               registryUrl: containerappswest7e0940.azurecr.io
               registryUsername: ${{ secrets.CLASSROOMTRANSCRIPTS_REGISTRY_USERNAME }}
               registryPassword: ${{ secrets.CLASSROOMTRANSCRIPTS_REGISTRY_PASSWORD }}
               containerAppName: classroom-transcripts
               resourceGroup: container-apps-west
               imageToBuild: containerappswest7e0940.azurecr.io/classroom-transcripts:${{ github.sha }}
     ```

By following these steps, you can automate the creation and deployment of Azure resources for the project.
