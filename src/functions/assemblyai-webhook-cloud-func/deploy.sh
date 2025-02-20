gcloud functions deploy assemblyai-webhook \
  --gen2 \
  --runtime=python39 \
  --region=us-west1 \
  --source=. \
  --entry-point=handle_assemblyai_webhook \
  --trigger-http \
  --allow-unauthenticated \
  --set-env-vars "BUCKET_NAME=$(grep BUCKET_NAME .env | cut -d= -f2),\
GOOGLE_CLOUD_PROJECT=$(grep GOOGLE_CLOUD_PROJECT .env | cut -d= -f2),\
ASSEMBLYAI_WEBHOOK_AUTH_HEADER_VALUE=$(grep ASSEMBLYAI_WEBHOOK_AUTH_HEADER_VALUE .env | cut -d= -f2),\
DRIVE_FOLDER_ID=$(grep DRIVE_FOLDER_ID .env | cut -d= -f2),\
ASSEMBLYAI_API_KEY=$(grep ASSEMBLYAI_API_KEY .env | cut -d= -f2)" | cat
