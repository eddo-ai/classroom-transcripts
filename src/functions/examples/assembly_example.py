import assemblyai as aai
import os

# Add debug logging
print(f"Current working directory: {os.getcwd()}")
print(f"Environment variables available: {os.environ.get('ASSEMBLYAI_API_KEY')}")

# Set API key in environment variables as 
api_key = os.getenv("ASSEMBLYAI_API_KEY")
print(f"API key loaded: {'Yes' if api_key else 'No'}")

if not api_key:
    raise ValueError("ASSEMBLYAI_API_KEY not found in environment variables")

aai.settings.api_key = api_key

transcriber = aai.Transcriber()

# local file - this will need to be a publicly accessible URL

audio_url = "tests/fixtures/audio/short-classroom-sample.m4a"

# this step adds speaker labels, diarization, we want to add timestamps, and PII Redaction

config = aai.TranscriptionConfig(speaker_labels=True, timestamps=True).set_redact_pii(
    policies=[
        aai.PIIRedactionPolicy.person_name,
        aai.PIIRedactionPolicy.organization,
    ],
    substitution=aai.PIISubstitutionPolicy.hash,
)

# lets you know what will be transcribed
transcript = transcriber.transcribe(audio_url, config)

# handles errors
if transcript.status == aai.TranscriptStatus.error:
    print(f"Transcription failed: {transcript.error}")
    exit(1)

# we need to work on formatting here
for utterance in transcript.utterances:
    timestamp = utterance.start_time.strftime("%H:%M:%S")
    print(f"{timestamp} - Speaker {utterance.speaker}: {utterance.text}")
