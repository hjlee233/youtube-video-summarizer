# 개인용 YouTube 영상 요약 앱 MVP 기획안

작성일: 2026-06-20  
가칭: **TubeNote Local**

> **구현 현황 (2026-06-20):** 1~5단계(CLI 파이프라인 · Streamlit UI · 로그인/멤버십 영상 · 보안 정리 ·
> 화자 분리) 및 P1(동일 영상 캐시 · 중단 후 재개) 구현 완료. 멤버십/보호 영상은 Firefox 쿠키 + Deno +
> EJS 솔버로 지원한다. 화자 분리는 pyannote 기반 선택 기능(`--extra diarization` + HF_TOKEN).
> 실제 사용법·구조는 [README](../README.md) 참고. (이 문서는 원본 기획안)

## 1. 프로젝트 개요

YouTube 영상 URL을 입력하면 로컬 PC에서 오디오를 임시로 확보하고, 음성을 텍스트로 변환한 뒤 AI가 영상 내용을 구조적으로 요약해 Markdown 문서로 저장하는 개인용 애플리케이션을 개발한다.

외부 서비스로 배포하지 않으며 단일 사용자가 자신의 PC에서 실행하는 것을 전제로 한다. 로그인 영상은 사용자가 현재 로그인한 브라우저 세션을 선택적으로 활용하며, 인증 정보와 원본 미디어는 외부 서버나 별도 저장소에 영구 보관하지 않는다.

## 2. 목표

### 핵심 목표

1. YouTube URL 하나로 전체 처리 과정을 실행한다.
2. 한국어와 영어 영상에서 타임스탬프가 포함된 대본을 생성한다.
3. 긴 영상도 구간별 요약 후 전체 요약으로 통합한다.
4. 요약 항목에서 YouTube의 해당 시점으로 이동할 수 있게 한다.
5. 처리 결과를 사람이 읽기 좋은 Markdown 파일과 재처리 가능한 JSON 파일로 저장한다.
6. 원본 오디오와 중간 파일은 처리 완료 후 기본적으로 삭제한다.

### 성공 기준

- 60분 길이의 일반적인 강의 또는 인터뷰 영상을 중단 없이 처리할 수 있다.
- 결과 문서에 핵심 요약, 시간순 목차, 상세 내용, 결론 및 실행 항목이 포함된다.
- 모든 주요 요약 항목에 최소 하나의 근거 타임스탬프가 연결된다.
- 중간에 실패해도 다운로드나 STT 등 완료된 단계부터 재개할 수 있다.
- API 키와 브라우저 인증 정보가 로그 및 결과 문서에 노출되지 않는다.

## 3. 사용자와 사용 시나리오

### 대상 사용자

- 단일 개인 사용자
- Windows PC 사용자
- 강의, 인터뷰, 토론, 기술 발표 등을 빠르게 정리하려는 사용자

### 기본 시나리오

1. 앱을 실행한다.
2. YouTube URL을 입력한다.
3. 공개 영상 또는 로그인 필요 여부를 선택한다.
4. 요약 방식과 음성 인식 모델을 선택한다.
5. `분석 시작`을 누른다.
6. 다운로드, 음성 인식, 화자 분리, 요약 진행률을 확인한다.
7. 완성된 요약과 대본을 화면에서 확인한다.
8. Markdown 또는 JSON 파일을 연다.

## 4. MVP 범위

### 반드시 구현

- YouTube URL 입력 및 형식 검증
- `yt-dlp`를 이용한 오디오 전용 다운로드
- 공개 영상 처리
- 선택적 `--cookies-from-browser` 사용
- FFmpeg 기반 16 kHz mono WAV 전처리
- `faster-whisper` 기반 음성 인식
- 문장 또는 세그먼트별 시작·종료 시간 저장
- 긴 대본 청크 분할
- LLM을 이용한 청크 요약 및 최종 통합 요약
- 타임스탬프 YouTube 링크 생성
- Markdown 및 JSON 결과 저장
- 처리 단계별 상태와 오류 표시
- 임시 미디어 자동 삭제
- 동일 영상 재처리 시 기존 결과 감지

### 설정으로 제공

- STT 모델: `small`, `medium`, `large-v3`
- 실행 장치: 자동, CPU, CUDA
- 요약 제공자: OpenAI 호환 API 또는 Ollama
- 요약 유형: 간단, 표준, 상세
- 음원 및 대본 보존 여부
- 브라우저: Chrome, Edge, Firefox
- 영상 언어: 자동 감지, 한국어, 영어

### 2차 버전

- WhisperX 정밀 단어 타임스탬프
- pyannote 화자 분리
- 화자 이름 수동 변경
- 영상 내 질문과 답변
- 여러 영상 일괄 처리
- 대본 편집 UI
- 검색 및 태그
- 자막 파일 SRT/VTT 출력

### MVP에서 제외

- 외부 서버 배포
- 사용자 계정 및 권한 관리
- 모바일 앱
- 실시간 스트리밍 처리
- DRM 또는 접근 제한 우회
- 영상 파일 영구 보관
- 여러 PC 사이의 동기화
- 자동 번역 및 더빙
- 화자 음원 자체를 분리하는 source separation

## 5. 권장 기술 스택

| 영역 | 기술 | 선택 이유 |
|---|---|---|
| 언어 | Python 3.11 | 미디어·AI 라이브러리 생태계 |
| UI | Streamlit | 개인용 MVP를 빠르게 구현 가능 |
| 다운로드 | yt-dlp | 오디오 및 메타데이터 처리 |
| 미디어 전처리 | FFmpeg/ffprobe | 포맷, 채널, 샘플레이트 변환 |
| 음성 인식 | faster-whisper | Whisper 대비 빠르고 메모리 효율적 |
| 음성 구간 검출 | Silero VAD 내장 옵션 | 무음 구간 제거 |
| 화자 분리 | WhisperX + pyannote, 2차 | 초기 복잡도와 GPU 사용량 절감 |
| 요약 | OpenAI 호환 API 또는 Ollama | 클라우드와 로컬 모델 모두 지원 |
| 데이터 저장 | 파일 기반 JSON | 단일 사용자 MVP에 DB 불필요 |
| 설정 | `.env` + `config.yaml` | 비밀 정보와 일반 설정 분리 |
| 테스트 | pytest | 모듈별 자동 검증 |
| 패키지 관리 | uv | 빠른 환경 구성과 잠금 파일 |

## 6. 시스템 구조

```text
[Streamlit UI]
      |
      v
[Job Controller]
      |
      +--> URL 검사 / 영상 ID 추출
      +--> yt-dlp 메타데이터 조회
      +--> 오디오 다운로드
      +--> FFmpeg 전처리
      +--> faster-whisper STT
      +--> 대본 정규화 및 청크 분할
      +--> LLM 청크 요약
      +--> LLM 최종 통합
      +--> Markdown / JSON 출력
      +--> 임시 파일 정리
```

각 단계는 독립 모듈로 만들고, 단계가 끝날 때마다 상태 파일을 기록한다. 앱이 중단되면 상태 파일을 읽어 마지막 성공 단계 다음부터 재개한다.

## 7. 권장 디렉터리 구조

```text
tubenote-local/
├─ app.py
├─ pyproject.toml
├─ uv.lock
├─ .env.example
├─ config.example.yaml
├─ README.md
├─ src/
│  └─ tubenote/
│     ├─ __init__.py
│     ├─ config.py
│     ├─ models.py
│     ├─ pipeline.py
│     ├─ youtube.py
│     ├─ audio.py
│     ├─ transcriber.py
│     ├─ transcript.py
│     ├─ summarizer.py
│     ├─ renderer.py
│     ├─ storage.py
│     └─ errors.py
├─ prompts/
│  ├─ chunk_summary.md
│  └─ final_summary.md
├─ tests/
│  ├─ test_youtube.py
│  ├─ test_transcript.py
│  ├─ test_chunking.py
│  └─ test_renderer.py
├─ data/
│  ├─ jobs/
│  ├─ results/
│  └─ temp/
└─ logs/
```

## 8. 핵심 처리 흐름

### 8.1 입력 검증

- `youtube.com/watch`, `youtu.be`, `youtube.com/live` URL 지원
- URL에서 영상 ID 추출
- 재생목록 URL은 MVP에서 첫 영상만 처리하거나 명시적으로 거절
- `yt-dlp --dump-single-json`으로 접근 가능 여부와 메타데이터 확인
- 생방송 중인 영상은 처리하지 않고 종료 후 다시 시도하도록 안내

### 8.2 메타데이터 수집

저장 항목:

- video ID
- 제목
- 채널명
- 원본 URL
- 영상 길이
- 게시일
- 썸네일 URL
- 감지된 라이브 여부
- 다운로드 및 처리 시각

### 8.3 오디오 확보

기본 정책:

- 최상의 오디오 스트림만 임시 다운로드
- 로그인 필요 시 사용자가 고른 브라우저에 대해 `--cookies-from-browser` 사용
- 쿠키 파일을 앱 디렉터리에 내보내거나 저장하지 않음
- 파일명에는 영상 ID를 사용해 특수문자 문제 방지

개념 명령:

```powershell
yt-dlp -f "bestaudio/best" --no-playlist -o "data/temp/%(id)s.%(ext)s" "<URL>"
```

로그인 영상:

```powershell
yt-dlp --cookies-from-browser edge -f "bestaudio/best" --no-playlist "<URL>"
```

### 8.4 오디오 전처리

```powershell
ffmpeg -y -i input.m4a -vn -ac 1 -ar 16000 -c:a pcm_s16le audio.wav
```

- mono
- 16 kHz
- PCM 16-bit WAV
- 원본 볼륨은 기본적으로 유지
- 음량 정규화와 잡음 제거는 실제 품질 문제를 확인한 뒤 추가

### 8.5 음성 인식

기본 설정:

```python
WhisperModel(
    model_size_or_path="medium",
    device="auto",
    compute_type="int8_float16"  # GPU
)
```

CPU에서는 `compute_type="int8"`을 사용한다.

권장 옵션:

- `vad_filter=True`
- `beam_size=5`
- 영상 언어를 사용자가 지정하면 `language` 전달
- hallucination 방지를 위해 무음 제거
- 세그먼트 시작·종료 시간과 텍스트를 모두 저장

### 8.6 대본 정규화

- 앞뒤 공백 정리
- 연속 공백 통합
- 빈 세그먼트 제거
- 매우 짧고 인접한 세그먼트 병합
- 원본 타임스탬프 보존
- 같은 문장이 반복되는 경우 중복 후보로 표시
- LLM이 대본 자체를 임의로 다시 쓰지 않도록 원문과 정리본을 구분

### 8.7 청크 분할

시간 기준이 아니라 텍스트 길이와 문장 경계를 함께 사용한다.

초기값:

- 청크당 약 6,000~8,000자
- 이전 청크와 1~2개 세그먼트 중첩
- 하나의 세그먼트를 중간에서 자르지 않음
- 각 청크에 시작·종료 시간 포함

### 8.8 요약

2단계 Map-Reduce 방식을 사용한다.

1. 각 청크에서 핵심 내용, 주장, 사례, 결론, 타임스탬프를 구조화해 추출한다.
2. 청크별 결과를 합쳐 전체 중복을 제거하고 최종 문서를 작성한다.

LLM 출력은 자유 텍스트보다 JSON 구조를 우선한다.

```json
{
  "summary": "구간 핵심 요약",
  "topics": [
    {
      "title": "주제",
      "detail": "설명",
      "timestamp_seconds": 754
    }
  ],
  "claims": [],
  "action_items": [],
  "uncertain_points": []
}
```

### 8.9 결과 렌더링

Markdown 문서 구성:

```text
# 영상 제목

- 채널
- 영상 URL
- 길이
- 처리 일시

## 세 줄 요약
## 핵심 내용
## 시간순 목차
## 상세 정리
## 주요 주장과 근거
## 결론
## 실행 항목
## 불확실하거나 확인이 필요한 내용
## 전체 대본
```

타임스탬프 링크:

```text
https://www.youtube.com/watch?v={VIDEO_ID}&t={SECONDS}s
```

## 9. 데이터 모델

### Job

```json
{
  "job_id": "uuid",
  "video_id": "abc123",
  "status": "transcribing",
  "completed_steps": ["metadata", "download", "audio"],
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "error": null,
  "settings": {
    "stt_model": "medium",
    "language": "auto",
    "summary_detail": "standard",
    "keep_audio": false
  }
}
```

### TranscriptSegment

```json
{
  "index": 0,
  "start": 12.4,
  "end": 18.7,
  "speaker": null,
  "text": "오늘은 인공지능 시장의 변화에 대해 이야기하겠습니다."
}
```

### Result

```json
{
  "metadata": {},
  "transcript": [],
  "chunk_summaries": [],
  "final_summary": {},
  "model_info": {
    "stt": "medium",
    "summarizer": "configured-model"
  }
}
```

## 10. 화면 설계

### 사이드바 설정

- STT 모델
- 언어
- CPU/GPU
- 요약 제공자와 모델
- 요약 상세도
- 로그인 브라우저
- 원본 오디오 보관 여부
- 전체 대본 포함 여부

### 메인 화면

1. URL 입력창
2. 영상 정보 미리보기
3. 분석 시작 버튼
4. 전체 진행률
5. 현재 단계와 경과 시간
6. 단계별 로그 요약
7. 결과 탭

결과 탭:

- 요약
- 시간순 목차
- 상세 정리
- 전체 대본
- 원본 JSON

## 11. 상태와 오류 처리

| 상황 | 사용자 메시지 | 처리 |
|---|---|---|
| 잘못된 URL | 지원하지 않는 YouTube 주소입니다 | 실행 중단 |
| 비공개/로그인 필요 | 브라우저 로그인이 필요합니다 | 브라우저 선택 안내 |
| 쿠키 접근 실패 | 브라우저를 종료하고 다시 시도하세요 | 재시도 가능 |
| FFmpeg 없음 | FFmpeg 설치 또는 경로 설정이 필요합니다 | 진단 정보 표시 |
| GPU 메모리 부족 | 더 작은 모델 또는 CPU로 다시 시도합니다 | 선택적 자동 폴백 |
| STT 중단 | 음성 인식 단계에서 실패했습니다 | 해당 단계 재시도 |
| API 키 없음 | 요약 API 설정이 필요합니다 | 대본까지만 저장 |
| LLM 호출 실패 | 요약 호출에 실패했습니다 | 청크 단위 재시도 |
| 토큰 초과 | 청크 크기를 줄여 다시 처리합니다 | 자동 재분할 |
| 앱 종료 | 완료 단계까지 상태를 저장했습니다 | 다음 실행에서 재개 |

재시도 정책:

- 네트워크 및 LLM 오류는 지수 백오프로 최대 3회
- 인증 및 설정 오류는 자동 재시도하지 않음
- 청크 하나의 요약 실패가 전체 대본과 다른 청크 결과를 삭제하지 않음

## 12. 개인정보 및 로컬 보안

- `.env`는 Git에서 제외
- API 키를 UI, 로그, JSON 결과에 기록하지 않음
- 브라우저 쿠키를 직접 복사하거나 파일로 저장하지 않음
- 하위 프로세스 명령 로그에서 민감 인자 마스킹
- 원본 오디오 기본 자동 삭제
- 임시 폴더 정리 버튼 제공
- 클라우드 LLM 사용 시 대본이 해당 제공자에게 전송된다는 안내 표시
- 완전 로컬 처리가 필요하면 Ollama 사용

## 13. 설정 파일 예시

`.env.example`

```dotenv
OPENAI_API_KEY=
OPENAI_BASE_URL=
```

`config.example.yaml`

```yaml
paths:
  data_dir: data
  temp_dir: data/temp
  result_dir: data/results

transcription:
  model: medium
  device: auto
  language: auto
  vad_filter: true
  beam_size: 5

summary:
  provider: openai_compatible
  model: ""
  detail: standard
  chunk_chars: 7000
  max_retries: 3

privacy:
  keep_audio: false
  include_full_transcript: true
```

## 14. 요약 프롬프트 요구사항

### 청크 요약 프롬프트

- 제공된 대본 안의 정보만 사용
- 추측과 외부 지식 추가 금지
- 중요한 주장마다 근거 시간 기록
- 광고, 인사말, 반복 발언은 중요도 낮게 처리
- 고유명사나 숫자가 불확실하면 `확인 필요`로 표시
- JSON 스키마를 지켜 출력

### 최종 통합 프롬프트

- 청크 간 중복 제거
- 영상의 전개 순서 유지
- 핵심 주장과 사례를 구분
- 영상에서 실제로 나온 결론과 모델이 만든 해석을 구분
- 실행 항목이 명시되지 않았다면 억지로 생성하지 않음
- 각 주요 항목에 원본 시간 연결

## 15. 개발 단계

### 1단계: CLI 수직 기능 구현

목표: URL 하나를 입력해 Markdown 결과까지 생성한다.

- 프로젝트 및 설정 구조 생성
- URL/영상 ID 파서
- yt-dlp 메타데이터 및 다운로드
- FFmpeg 변환
- faster-whisper STT
- JSON 대본 저장
- 단일 LLM 요약
- Markdown 생성
- 임시 파일 정리

완료 조건:

```powershell
uv run python -m tubenote.cli "<YOUTUBE_URL>"
```

명령 하나로 결과 파일이 생성된다.

### 2단계: 긴 영상 안정화

- 청크 분할
- 구간별 요약
- 최종 통합
- 실패 청크 재시도
- 작업 상태 저장과 재개
- 동일 영상 캐시

완료 조건:

- 60분 영상을 처리한다.
- 요약 도중 앱이 종료되어도 처음부터 STT를 다시 하지 않는다.

### 3단계: Streamlit UI

- URL 입력
- 설정 UI
- 영상 미리보기
- 진행률
- 결과 탭
- 파일 열기 및 다운로드
- 실패 단계 재시도 버튼

완료 조건:

```powershell
uv run streamlit run app.py
```

명령으로 개인용 앱을 사용할 수 있다.

### 4단계: 로그인 영상과 보안

- 브라우저 선택
- `cookies-from-browser`
- 민감 정보 로그 마스킹
- 임시 파일 일괄 정리
- 클라우드 전송 안내

### 5단계: 선택적 화자 분리

- WhisperX 도입
- pyannote 설정
- 화자별 대본 병합
- 화자 이름 변경 UI
- 화자별 핵심 주장 출력

## 16. 우선순위별 작업 목록

### P0

- 프로젝트 초기화
- 설정 로딩
- URL 검증
- 메타데이터 조회
- 오디오 다운로드
- FFmpeg 변환
- STT 실행
- 대본 JSON 저장
- 청크 분할
- 요약 호출
- Markdown 렌더링
- 임시 파일 정리

### P1

- 진행 상태 저장
- 중단 후 재개
- Streamlit UI
- 로그인 브라우저 지원
- LLM 재시도
- GPU OOM 폴백
- 동일 영상 재사용

### P2

- 화자 분리
- Ollama 모델 자동 탐색
- SRT/VTT 출력
- 영상 Q&A
- 여러 영상 큐

## 17. 테스트 계획

### 단위 테스트

- 각 YouTube URL 형식에서 영상 ID 추출
- 타임스탬프 링크 생성
- 빈 세그먼트 제거
- 인접 세그먼트 병합
- 청크 크기 제한
- Markdown 특수문자 처리
- 설정 누락 및 기본값

### 통합 테스트

- 5분 공개 한국어 영상
- 30분 1인 강의
- 60분 인터뷰
- 영어 영상
- 무음이 긴 영상
- 접근 불가능한 영상
- 로그인 필요한 영상
- LLM API 일시 실패
- GPU 메모리 부족

### 수동 품질 평가

- 주요 주제가 빠지지 않았는가
- 요약에 원문에 없는 사실이 추가되지 않았는가
- 시간 링크가 실제 발언 위치와 근접한가
- 숫자와 고유명사가 대본과 일치하는가
- 광고와 반복 발언이 과도하게 강조되지 않았는가

## 18. MVP 완료 정의

다음 조건을 모두 만족하면 MVP 완료로 본다.

- Windows에서 설치 문서대로 실행 가능
- 공개 URL과 선택적 브라우저 로그인 URL 입력 가능
- 오디오, STT, 요약 파이프라인 정상 작동
- 60분 영상 처리 성공
- Markdown 및 JSON 생성
- 요약에 클릭 가능한 타임스탬프 포함
- API 키와 쿠키가 저장·출력되지 않음
- 기본 설정에서 임시 오디오 자동 삭제
- 실패 단계 재시도 또는 재개 가능
- 핵심 모듈 단위 테스트 통과

## 19. 예상 개발 일정

개인 개발 기준의 대략적인 일정이다.

| 기간 | 결과 |
|---|---|
| 1일차 | 프로젝트 구조, URL 검사, yt-dlp, FFmpeg |
| 2일차 | faster-whisper 대본 생성과 JSON 저장 |
| 3일차 | 청크 분할, LLM 요약, Markdown |
| 4일차 | 상태 저장, 오류 처리, 재시도 |
| 5일차 | Streamlit UI |
| 6일차 | 로그인 영상, 보안 및 정리 |
| 7일차 | 테스트, 문서화, 품질 조정 |

화자 분리는 MVP 안정화 후 별도 2~3일 작업으로 잡는다.

## 20. 바로 착수할 첫 번째 작업

첫 커밋의 목표는 “5분짜리 공개 영상에서 대본 JSON을 얻는 것”이다.

1. `uv init`
2. `src/tubenote` 패키지 생성
3. `yt-dlp`, `faster-whisper`, `pydantic-settings` 설치
4. FFmpeg 존재 여부 검사
5. URL에서 메타데이터 조회
6. 오디오 다운로드
7. WAV 변환
8. STT 세그먼트를 JSON으로 저장
9. 테스트 영상 하나로 실행 검증

첫 커밋에서는 UI, LLM, 화자 분리를 넣지 않는다. 다운로드부터 대본 생성까지의 가장 위험한 기술 경로를 먼저 검증한다.

