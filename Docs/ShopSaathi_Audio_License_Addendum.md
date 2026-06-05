# ShopSaathi / GharStock AI — Audio + License Addendum

## 1. Hackathon license stance

For the Build Small Hackathon submission, non-commercial or research-only models may be used when they materially improve the experience, especially for grounding, segmentation, image understanding, or voice.

The README and Space card must disclose the scope clearly:

> Some model weights are used under research/non-commercial terms for hackathon evaluation. Commercial use would require replacing or relicensing those modules.

This means the product can use attractive research models such as LocateAnything-style grounding or RMBG-style segmentation for the hackathon artifact, while still documenting commercially compatible alternatives for a later production path.

Do not hide license limits. Treat them as transparent product notes, not blockers.

## 2. Do not anchor the voice layer to Whisper

Whisper remains a useful baseline, but ShopSaathi should not be described as “using Whisper for voice.” Voice is central to the product: parents, neighbours, and household members should be able to ask while shopping, correct detections hands-free, and hear short answers.

The product should be described as having a swappable voice layer:

> ShopSaathi includes a model-swappable voice layer. The submitted build benchmarks current small STT/TTS models and uses the best-performing local stack for household shopping commands.

## 3. Voice requirements for ShopSaathi

The voice layer should optimize for:

- short household commands
- noisy market/shop environments
- Indian English, Hinglish, Hindi, and optionally Kannada/Tamil/Telugu/Marathi/Bengali
- correction phrases
- low latency
- local/off-grid operation when possible
- ≤32B total model parameter accounting
- Gradio/Hugging Face Space deployability

Representative utterances:

```text
Doodh ghar pe hai kya?
Aaj kya kharidna hai?
Yeh tamatar aadha kilo add karo.
Nahi, yeh aloo nahi pyaaz hai.
Bread expiry kal ka hai, skip kar do.
Surf Excel already ghar pe hai kya?
Is packet ka MRP kitna hai?
Fridge mein dahi kab expire hoga?
Kal breakfast ke liye kya hai?
List se chawal hata do.
```

## 4. STT model candidates to evaluate

### Qwen3-ASR-1.7B

Strong candidate for current small-model ASR. It should be tested for short Indian household commands, Hinglish, Hindi, and correction utterances.

Use cases:

- shopping list creation
- quantity corrections
- inventory search
- packet/list commands

### NVIDIA Nemotron / Parakeet 0.6B streaming ASR

Attractive for market-mode and near-live shopping interaction because the model family is streaming-oriented and small. Test install/runtime friction in Spaces before relying on it.

Use cases:

- quick spoken market questions
- short confirmations
- low-latency voice flows

### Mistral Voxtral Mini Realtime

Useful to test if we want voice-agent behavior rather than only plain transcription. Potentially good for direct speech understanding and voice command interpretation.

### FunAudioLLM SenseVoiceSmall

Worth testing as a compact Whisper alternative. It may be useful for short commands, real-time interaction, and richer audio cues.

### VibeVoice ASR / Cohere Transcribe / Granite Speech

Secondary evaluation candidates. Include them if setup and runtime are comfortable.

### Whisper large-v3-turbo

Keep as the reliable baseline, not the default ambition. If newer models fail install/runtime/quality tests, Whisper can still carry the voice layer.

## 5. TTS model candidates to evaluate

### OpenMOSS MOSS-TTS-v1.5

Strong current multilingual TTS candidate. Good fit if voice output needs warmth and language coverage.

### VoxCPM2

Attractive because OpenBMB is an anchor sponsor and the model family aligns with the hackathon ecosystem. Good candidate for multilingual voice and voice-design behavior.

### Qwen3-TTS 0.6B / 1.7B

Strong if we want a Qwen-centered stack. The 0.6B version is appealing for parameter budget; the 1.7B version should be tested for better voice quality.

### Higgs Audio v3 TTS 4B

Interesting for expressive voice-agent output. Use only if setup and latency are acceptable.

### Kokoro-82M

Tiny, useful fallback. Not the most ambitious, but good for fast local responses and reliability.

### CosyVoice / other FunAudioLLM TTS

Evaluate if multilingual output quality and deployment are good.

## 6. Voice-to-voice architecture

```text
Voice input
  → STT provider
  → intent parser / tool-call planner
  → inventory + shopping-list + household-map tools
  → short answer generator
  → TTS provider
```

Voice should not be a gimmick. The product feature is hands-free shopping conversation.

Example:

User says:

> Yeh packet lena chahiye kya?

The system checks:

- visible item from image/video
- shopping list
- home inventory
- expiry/OCR if visible
- price memory if available

Then answers:

> Agar yeh bread hai, lo. Bread list mein hai. Expiry date check kar lo — photo mein clear nahi dikh raha.

## 7. ShopSaathi Voice Bench

Create a small benchmark script and report so the voice choice is evidence-based.

Suggested file:

```text
scripts/voice_bench.py
```

Benchmark inputs:

- recorded voice clips from the actual household user
- clean microphone clips
- noisy market-like clips
- text fixtures for expected intent

Score STT on:

- transcription accuracy
- intent preservation
- Hindi/Hinglish handling
- noisy audio tolerance
- latency
- memory use
- install/runtime pain
- Space compatibility

Score TTS on:

- clarity
- pronunciation of Indian grocery words and names
- Hinglish comfort
- warmth/trust
- speed
- install/runtime pain
- Space compatibility

## 8. Provider interfaces for agents

Do not hardcode a single speech model.

Implementation should include:

```text
shopsaathi/voice/base.py
shopsaathi/voice/providers/mock_stt.py
shopsaathi/voice/providers/qwen_asr.py
shopsaathi/voice/providers/parakeet_asr.py
shopsaathi/voice/providers/whisper_baseline.py
shopsaathi/voice/providers/mock_tts.py
shopsaathi/voice/providers/kokoro_tts.py
shopsaathi/voice/providers/qwen_tts.py
shopsaathi/voice/providers/moss_tts.py
scripts/voice_bench.py
```

Provider interface sketch:

```python
class STTProvider:
    name: str
    model_id: str
    parameter_count: int | None
    license: str | None

    def transcribe(self, audio_path: str, language_hint: str | None = None) -> dict:
        ...

class TTSProvider:
    name: str
    model_id: str
    parameter_count: int | None
    license: str | None

    def synthesize(self, text: str, language_hint: str | None = None, voice: str | None = None) -> str:
        ...
```

The app should support environment or config selection:

```text
SHOPSAATHI_STT_PROVIDER=qwen_asr
SHOPSAATHI_TTS_PROVIDER=moss_tts
```

Tests should use mock providers.

## 9. README update

Add a dedicated section:

```markdown
## Voice model evaluation

ShopSaathi does not assume Whisper is the best voice layer. The submitted build includes a swappable STT/TTS provider interface and a small household-shopping voice benchmark. Whisper is retained as a baseline, while Qwen3-ASR, Parakeet/Nemotron, Voxtral, SenseVoice, MOSS-TTS, VoxCPM2, Qwen3-TTS, and Kokoro are considered or tested based on deployability.
```

## 10. Updated model philosophy

The product should say:

> ShopSaathi is model-modular. Perception, speech, reasoning, OCR, segmentation, image editing, and TTS can be swapped as the small-model ecosystem improves.

Not:

> ShopSaathi uses Whisper and a chatbot.

This matters because the hackathon is partly about showing how capable the new small-model ecosystem is.
