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
