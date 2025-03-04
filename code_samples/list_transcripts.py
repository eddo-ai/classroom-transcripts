# Start by making sure the `assemblyai` package is installed.
# If not, you can install it by running the following command:
# pip install -U assemblyai
#
# Note: Some macOS users may need to use `pip3` instead of `pip`.
# %%
import os
import assemblyai as aai

# %%
# Replace with your API key
aai.settings.api_key = "24757ca079da4ccda80cc791fae28ec1"

# Check if the request was successful
transcriber = aai.Transcriber()
params = aai.ListTranscriptParameters()
page = transcriber.list_transcripts(params)
page.transcripts

# %%
# Get the first transcript id
transcript = page.transcripts[0]
transcript.id

# %%
# Get the transcript by id
transcript = aai.Transcript.get_by_id(transcript.id)
transcript.text

# %%
