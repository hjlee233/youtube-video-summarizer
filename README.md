# TubeNote Local

개인용 YouTube 영상 요약 앱. YouTube URL을 입력하면 로컬 PC에서 오디오를 임시로
내려받아 음성을 텍스트로 변환하고, AI가 내용을 구조적으로 요약해 Markdown/JSON으로
저장한다. 외부 서버로 배포하지 않으며 단일 사용자의 PC 실행을 전제로 한다.

> 자세한 기획은 [docs/youtube-video-summarizer-mvp-plan.md](docs/youtube-video-summarizer-mvp-plan.md) 참고.

## 현재 진행 상황

**1~5단계 + P1** — CLI(다운로드 → STT → 청크 분할 → LLM 요약(Map-Reduce) → Markdown/JSON),
**Streamlit UI**, **로그인 영상·보안 정리**(브라우저 쿠키, 민감정보 마스킹, 클라우드 전송 안내,
임시 폴더 정리), **동일 영상 캐시·중단 후 재개**, **화자 분리(pyannote, 선택)**까지 구현.
요약 자격증명이 없으면 대본까지만 저장한다.

> **캐시/재개:** 같은 영상을 다시 처리하면 `result.json`의 대본을 재사용해 다운로드·STT를 건너뛴다.
> 요약 도중 중단되었다면 STT 재실행 없이 요약부터 이어간다. `--reprocess`(CLI) 또는 UI의
> "강제 재처리"로 캐시를 무시할 수 있다.

## 사전 요구사항

- Python 3.11+ (uv가 자동으로 설치)
- [uv](https://docs.astral.sh/uv/)
- [FFmpeg](https://www.gyan.dev/ffmpeg/builds/) (PATH에 등록)
- (선택) NVIDIA GPU + CUDA — STT 가속용
- (선택) [Deno](https://deno.land) — 멤버십/보호 영상의 JS 챌린지 해석용
- (선택) 요약 LLM — OpenAI 호환 API 키 또는 로컬 Ollama/vLLM

## 설치

```powershell
uv sync
```

처음 STT를 실행하면 faster-whisper가 모델 가중치를 자동으로 내려받는다.

## UI 실행 (Streamlit)

```powershell
uv run streamlit run app.py
```

브라우저에서 사이드바 설정 → URL 입력 → 미리보기 → 분석 시작 → 결과 탭(요약/목차/상세/대본/JSON)
순으로 사용한다. 진행률과 단계별 로그가 실시간 표시되며, summary.md·result.json 다운로드와
결과 폴더 열기를 지원한다.

> **Windows 포트 주의:** 기본 포트 8501이 Hyper-V/WSL 예약 범위(`netsh int ipv4 show
> excludedportrange protocol=tcp`로 확인)에 걸려 `Port 8501 is not available`가 날 수 있다.
> 이때 예약 범위 밖 포트를 지정한다: `uv run streamlit run app.py --server.port 8800`

## CLI 사용법

```powershell
uv run python -m tubenote.cli "https://www.youtube.com/watch?v=VIDEO_ID"
```

주요 옵션:

| 옵션 | 설명 |
|---|---|
| `--model` | STT 모델: `small` / `medium` / `large-v3` |
| `--language` | 언어: `auto` / `ko` / `en` / `ja` |
| `--device` | 실행 장치: `auto` / `cpu` / `cuda` |
| `--compute-type` | 연산 정밀도: `auto` / `int8` / `int8_float16` / `float16` / `float32` |
| `--keep-audio` | 처리 후 임시 오디오 보존 |
| `--cookies-from-browser` | 로그인 영상용 브라우저 (`chrome`/`edge`/`firefox`) |
| `--allow-remote-components` | 멤버십/보호 영상의 JS 챌린지 해석 허용 (Deno + 외부 JS 솔버) |
| `--no-summary` | LLM 요약을 건너뛰고 대본만 생성 |
| `--reprocess` | 캐시(기존 결과)를 무시하고 다운로드·STT부터 강제 재처리 |
| `--diarize` | 화자 분리(pyannote) 수행 (`--extra diarization` + HF_TOKEN 필요) |
| `--provider` | 요약 제공자: `openai_compatible` / `ollama` |
| `--summary-model` | 요약 LLM 모델명 |
| `--detail` | 요약 상세도: `simple` / `standard` / `detailed` |
| `--clean-temp` | 임시 폴더(`data/temp`)를 비우고 종료 (URL 없이 사용) |

결과는 `data/results/<video_id>/`에 저장된다:
- `result.json` — 메타데이터 · **전체 대본** · 청크 요약 · 최종 요약 (재처리·대본 보관용)
- `summary.md` — 사람이 읽기 좋은 요약 Markdown. 섹션: 세 줄 요약 · 핵심 내용 · 시간순 목차 ·
  **서사 요약**(산문형) · 상세 정리 · 주요 주장과 근거 · 결론 · 실행 항목 · 불확실한 내용
  (모든 항목에 클릭 가능한 타임스탬프 링크)

> `summary.md`에는 기본적으로 전체 대본을 넣지 않는다(`privacy.include_full_transcript: false`).
> 대본 원문은 항상 `result.json`에 보존되며, 별도 대본/자막(SRT·VTT) 내보내기 기능은 향후 과제로 둔다.

### GPU(CUDA) 사용

NVIDIA GPU가 있으면 `--device cuda`(또는 `auto`)로 가속한다. CTranslate2가 CUDA 12용
cuBLAS와 cuDNN 9를 필요로 하며, 환경에 따라 별도 설치가 필요할 수 있다. VRAM이 충분한
GPU(예: 24GB)에서는 `--compute-type float16`이 품질·속도 면에서 권장된다.

## 요약(LLM) 설정

요약을 사용하려면 제공자와 모델을 설정해야 한다. 미설정 시 대본까지만 저장된다.

**OpenAI 호환 API** — `.env`에 키를 넣고 `config.yaml`에서 모델 지정:

```dotenv
# .env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=        # 호환 엔드포인트 사용 시에만
```

```powershell
uv run python -m tubenote.cli "<URL>" --summary-model gpt-4o-mini
```

**Ollama (완전 로컬)** — Ollama 실행 후:

```powershell
uv run python -m tubenote.cli "<URL>" --provider ollama --summary-model llama3.1
```

> 클라우드 API를 쓰면 대본이 해당 제공자에게 전송된다. 완전 로컬 처리가 필요하면 Ollama를 사용한다.

## 로그인 / 멤버십·보호 영상

1. **로그인 영상**: 해당 계정으로 로그인한 브라우저를 `--cookies-from-browser`(또는 UI 사이드바)로
   지정한다. **Chrome 127+ 는 App-Bound Encryption + 실행 중 DB 잠금** 때문에 쿠키 추출이 실패할
   수 있으니, **Firefox 사용을 권장**한다(ABE 없음, 실행 중에도 읽힘).
2. **멤버십/보호 영상**: YouTube의 JS 서명 챌린지를 풀어야 스트림 포맷이 보인다. 이를 위해
   - **[Deno](https://deno.land) 설치** (`winget install DenoLand.Deno`), 그리고
   - `--allow-remote-components`(또는 UI 체크박스)로 yt-dlp가 외부 JS 솔버(yt-dlp-ejs)를 GitHub에서
     받아 Deno로 실행하도록 허용한다.

   > ⚠️ 이 옵션은 **외부 JavaScript를 내려받아 실행**하므로 기본 비활성이다. 필요한 영상에만 켠다.
   > 생방송 중인 영상은 처리하지 않는다(다시보기는 가능).

## 화자 분리 (선택)

여러 화자가 등장하는 영상에서 발화자를 구분한다(pyannote.audio). 무거운 선택 기능이라 기본 OFF.

1. **설치**: `uv sync --extra diarization` (pyannote.audio + **CUDA torch(cu128)** 등 — 수 GB).
   `pyproject.toml`에 CUDA 인덱스가 설정돼 있어 NVIDIA GPU에서 자동 가속된다.
2. **HF 토큰**: `.env`에 `HF_TOKEN=hf_...` 추가
3. **라이선스 동의**: HuggingFace에서 `pyannote/speaker-diarization-3.1`,
   `pyannote/segmentation-3.0` 모델 약관에 동의(접속 후 1회)
4. 실행: `--diarize`(CLI) 또는 UI "화자 분리 (pyannote)" 체크

`device: auto`가 GPU를 자동 감지한다(없으면 CPU). 26분 영상 기준 **RTX 4090 약 1분 vs CPU 약 10분**.
torch는 pyannote 3.x 호환을 위해 2.7.x로 고정한다(torchaudio<2.8 `AudioMetaData`, hf_hub<1.0).

결과 대본의 각 줄에 `SPEAKER_00` 등 라벨이 붙고, UI의 **"화자 이름 변경"** 으로 실제 이름으로
바꿀 수 있다(변경 시 result.json·summary.md 갱신). 화자 라벨은 요약 프롬프트에도 전달되어
상세 요약에서 발화자별 주장 구분에 활용된다. pyannote 실패 시 화자 없이 대본만 생성된다.

> WhisperX 대신 pyannote를 직접 사용한다 — 기존 faster-whisper STT를 그대로 재사용하고
> 의존성 충돌을 피하기 위함. 화자는 STT 세그먼트에 시간 겹침 기준으로 배정된다.

## 설정

- 일반 설정: `config.yaml` (없으면 `config.example.yaml` 기본값 사용). `config.example.yaml`을 복사해 사용.
- 비밀 정보: `.env` (요약 API 키 `OPENAI_API_KEY`, 화자 분리 `HF_TOKEN`). `.env.example` 참고.
- `config.yaml` 값은 **CLI·UI의 기본값**을 함께 구동한다. CLI 옵션은 그때그때 이를 덮어쓴다.
- 주요 섹션: `transcription`(STT 모델·장치·정밀도·언어), `summary`(제공자·모델·상세도·청크 크기·
  `temperature`), `youtube`(기본 로그인 브라우저·원격 컴포넌트 허용), `privacy`(오디오 보관·대본 포함).
- `summary.temperature`는 기본 `0`(결정적)이다. OpenAI는 0에서도 완전 동일을 보장하진 않지만
  run 간 변동이 크게 줄어 충실 요약에 적합하다.

## 프로젝트 구조

```text
app.py                     # Streamlit UI
prompts/                   # 청크/최종 요약 프롬프트
src/tubenote/
├─ cli.py                  # CLI 진입점
├─ pipeline.py             # 전체 오케스트레이션 (메타→다운로드→STT→요약→렌더)
├─ config.py               # .env + config.yaml 로딩
├─ models.py               # 데이터 모델 (Job/Result/FinalSummary 등)
├─ errors.py               # 단계별 오류 + 한국어 사용자 메시지
├─ youtube.py              # URL 파싱·메타데이터·오디오 다운로드(쿠키/EJS)
├─ audio.py                # FFmpeg 16kHz mono WAV 변환
├─ transcriber.py          # faster-whisper STT
├─ transcript.py           # 대본 정규화
├─ chunking.py             # 텍스트/문장 경계 기반 청크 분할
├─ summarizer.py           # LLM Map-Reduce 요약 (OpenAI 호환/Ollama)
├─ renderer.py             # Markdown 렌더링
├─ storage.py              # JSON/MD 저장, 임시 폴더 정리
└─ security.py             # 비밀 마스킹, 클라우드 전송 판별
tests/                     # pytest (URL·정규화·청크·렌더·요약·보안·옵션)
data/results/<id>/         # result.json, summary.md
```

## 테스트

```powershell
uv run pytest
```

## 개인정보 / 보안 (기획안 12절)

- `.env`와 `config.yaml`은 Git에서 제외된다.
- API 키는 로그·오류 메시지·결과 파일(`result.json`)에 기록하지 않으며, 새어 나갈 수 있는
  오류 문자열은 자동 마스킹한다.
- 브라우저 쿠키는 `--cookies-from-browser`로 yt-dlp가 직접 읽으며, 파일로 복사·저장하지 않는다.
- 원본 오디오는 처리 후 기본 삭제된다 (`--keep-audio`로 보존 가능).
- 임시 폴더는 `--clean-temp`(CLI) 또는 UI의 "임시 폴더 정리" 버튼으로 일괄 비울 수 있다.
- **클라우드 LLM**(예: OpenAI)으로 요약하면 대본이 해당 제공자에게 전송된다 — CLI/UI에서 안내가
  표시된다. 완전 로컬 처리가 필요하면 Ollama 또는 로컬 vLLM을 사용한다.
