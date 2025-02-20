curl -X POST \
  -H "Content-Type: application/json" \
  -H "AssemblyAI-Signature-V1: $(echo -n '{"status":"completed","transcript_id":"test-123","text":"This is a test transcription","audio_url":"https://example.com/audio.mp3"}' | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | cut -d" " -f2)" \
  -d '{"status":"completed","transcript_id":"test-123","text":"This is a test transcription","audio_url":"https://example.com/audio.mp3"}' \
  https://us-west1-carnegie-learning.cloudfunctions.net/assemblyai-webhook
