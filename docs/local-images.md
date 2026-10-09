# RTX 4090 PC에서 이미지 생성하기

기존 서버 봇은 유지하고 GPU PC에서 `image_worker.py` 하나만 실행합니다.
현재 서버 봇은 `!그림`을 무시하므로 이 작업자만 이미지를 처리합니다.
동일 Discord 토큰을 사용하는 작업자는 PC 한 곳에서 한 개만 실행하세요.
기존 서버 봇에 이미지 명령을 추가할 때는 중복 응답 방지를 위해 이 작업자를 종료하세요.

## PC 준비 (Windows 기준)

1. 공식 ComfyUI Desktop을 설치합니다: https://docs.comfy.org/installation/desktop/windows
2. ComfyUI에서 SDXL 계열 체크포인트를 준비합니다. 모델 사용 조건을 확인하고,
   `.safetensors` 파일을 ComfyUI의 `models/checkpoints`에 둡니다.
   이 기본 워크플로는 SDXL용이며 FLUX 등 다른 구조 모델에는 사용할 수 없습니다.
   모델을 자동 다운로드하거나 구매하지 않습니다.
3. ComfyUI 기본 텍스트→이미지 워크플로로 먼저 1장을 생성합니다.
   본 작업자는 1024×1024, 25 steps, 한 장을 생성합니다. GPU 실제 속도는 미검증입니다.
4. ComfyUI 주소가 PC의 `127.0.0.1`인지 확인합니다. 표시된 포트(Desktop은 설치별로 다를 수 있음)를
   아래 `COMFYUI_PORT`에 넣습니다. 인증을 요구하는 서버는 현재 작업자가 지원하지 않습니다.
5. 저장소 PR이 반영된 코드를 PC에 내려받고 Python 3.11 이상에서 실행합니다.

PowerShell에서 저장소 폴더로 이동한 뒤:

```powershell
py -3.11 -m venv .venv-images
.\.venv-images\Scripts\python.exe -m pip install -r requirements-images.txt
$env:IMAGE_OWNER_ID = '본인의 Discord 사용자 ID'
$env:COMFYUI_CHECKPOINT = '설치한모델.safetensors'
$env:COMFYUI_PORT = '8188'
$secureToken = Read-Host 'Discord 봇 토큰' -AsSecureString
$env:DISCORD_TOKEN = [System.Net.NetworkCredential]::new('', $secureToken).Password
try {
    .\.venv-images\Scripts\python.exe image_worker.py
} finally {
    Remove-Item Env:DISCORD_TOKEN -ErrorAction SilentlyContinue
    $secureToken.Dispose()
}
```

Discord 설정의 개발자 모드를 켜고 본인 프로필의 사용자 ID 복사를 사용합니다.
Discord Developer Portal에서 기존 봇의 Message Content Intent가 켜져 있어야 합니다.
토큰을 채팅, 명령행 인수, 파일 또는 GitHub에 넣지 않습니다.

## 사용과 검증

### 안내식 실행

ComfyUI와 SDXL 모델을 준비한 다음 저장소 폴더의 PowerShell에서 실행합니다:

```powershell
powershell -NoProfile -File .\scripts\start-local-images.ps1
```

이 스크립트는 Python 버전과 ComfyUI 연결을 검사하고 설치된 모델 목록을 보여줍니다.
모델 번호·본인 Discord ID를 선택한 뒤 토큰을 숨김 입력으로 받고 작업자를 시작합니다.
가상환경과 의존성 설치에는 인터넷이 필요합니다. 종료 시 기존 환경변수를 복원합니다.
Windows에서 스크립트 실행이 제한되면 위의 수동 PowerShell 절차를 사용하세요.
보안 정책을 변경하지 않습니다. PowerShell 스크립트는 Windows 실제 실행 미검증입니다.

봇 DM에서 `!그림 a white sedan parked under cherry blossoms, anime illustration`을 보냅니다.
한국어 요청은 로컬 OPUS-MT 한국어→영어 모델로 번역한 뒤 SDXL에 전달합니다.
영어 요청은 그대로 전달합니다. 번역문은 요청자 DM에만 표시하고 로그에는 기록하지 않습니다.
번역기는 장면·스타일·소품을 추가하는 프롬프트 확장을 하지 않습니다. 번역 오류와 SDXL의
구도·세부사항 변동은 여전히 가능합니다. 짧고 구체적인 설명으로 번역문과 결과를 비교하세요.
번역 실패·너무 긴 입력·빈 출력 시 이미지를 생성하지 않습니다.

### 한국어 번역 준비 (PC에서 한 번)

```powershell
.\.venv-images\Scripts\python.exe -m pip install -r requirements-image-translation.txt
.\.venv-images\Scripts\python.exe image_prompt.py
```

준비 명령만 Hugging Face에서 고정 revision의 `Helsinki-NLP/opus-mt-ko-en`을 내려받습니다.
요청 중에는 로컬 캐시만 사용하고 외부 번역 API를 호출하지 않습니다. 번역은 CPU에서 처리해
ComfyUI GPU 메모리와 분리합니다. torch 설치 파일과 번역 모델 다운로드에 인터넷·디스크 공간이
필요합니다. 같은 Windows 계정으로 준비·실행하세요. API 키는 추가로 필요하지 않습니다.
설치 환경에 따라 다운로드·첫 모델 로딩에 시간이 걸릴 수 있습니다.
이 변경은 모의 번역으로 전달·실패 처리 테스트를 수행했습니다. 실제 한국어 번역 품질,
Windows 의존성 설치 및 생성 결과는 PC에서 준비 명령과 Discord 요청으로 확인해야 합니다.
공식 모델: https://huggingface.co/Helsinki-NLP/opus-mt-ko-en
결과 한 장을 DM으로 받으면 PC→ComfyUI→Discord 경로가 확인된 것입니다.
이미지 편집과 이전 이미지에 대한 대화는 이번 버전에서 지원하지 않습니다.

다른 사용자도 요청 가능하며 전역 동시 생성 1개, 사용자별 30초 대기시간, 최대 180초 대기,
첨부파일 8 MiB 제한입니다. 사용자별 제한 설정과 재시작 시 유지 방법은 아래를 참고하세요.
PC 또는 작업자를 끄면 이미지 명령에 응답하지 않습니다. 기존 텍스트 봇은 별도로 유지됩니다.
시간 초과 후 ComfyUI 작업은 계속될 수 있습니다. 다른 작업까지 끊지 않도록 전체 interrupt나
큐 삭제는 호출하지 않습니다. ComfyUI에서 완료 여부를 확인한 뒤 다시 요청하세요.

이미지와 프롬프트는 PC의 ComfyUI output/history에 남을 수 있고, 생성 이미지는 Discord로 전송됩니다.
로그에는 프롬프트·이미지·사용자 ID·토큰·예외 원문을 기록하지 않습니다.
공개 채널에 입력한 명령 자체는 공개되므로 민감한 요청은 DM을 사용하세요.
ComfyUI 포트의 인터넷 공개·공유기 포트 포워딩·외부 모델 API는 필요 없습니다.
로컬 모델은 건당 API 비용이 없지만 전기료와 PC 가동이 필요합니다.

공식 API: https://docs.comfy.org/development/comfyui-server/comms_routes
# Windows 로그인 자동 실행 (선택)

`python scripts/windows_image_startup.py`는 ComfyUI Desktop 실행 파일을 파일 선택 창으로
지정하고, 사용자 ID·포트·모델·기존 봇 토큰을 입력받습니다. Windows DPAPI CurrentUser로
토큰을 암호화하며 평문 토큰을 파일·로그·명령행에 저장하지 않습니다. 같은 PC의 같은
Windows 계정에서 로그인해야 복호화할 수 있습니다. 관리자 권한이나 실행 정책 변경은
필요하지 않습니다. 같은 계정으로 실행되는 프로그램까지 막는 보안 경계는 아닙니다.

설치 완료 후 기존 수동 이미지 worker를 Ctrl+C로 중지한 다음
`python scripts/windows_image_startup.py --start`로 시작하세요.
다음 로그인부터 사용자 시작프로그램 폴더의 `KeroroLocalImages.lnk`가 자동 실행됩니다.
감시 프로그램은 ComfyUI를 한 번 실행하고 로컬 API 준비를 기다린 뒤 worker를 실행하며,
worker 종료 시 60초 뒤 재시작합니다. ComfyUI 자체를 닫으면 다시 열어야 합니다.
절전·PC 종료·로그아웃 중에는 이미지 생성이 동작하지 않습니다.

상태는 `%LOCALAPPDATA%\KeroroLocalImages\status.txt`에 일반 문구만 기록합니다.
worker 프로세스 시작은 Discord 로그인이나 전송 성공의 증명이 아닙니다.
설정 파일과 암호화 토큰도 같은 폴더에 저장됩니다. 프로젝트 폴더를 이동·삭제하지 마세요.
자동 실행 해제는 `python scripts/windows_image_startup.py --remove`이며,
시작 바로가기와 암호화 토큰·설정을 삭제하고 감시 worker를 중지합니다. ComfyUI는 유지합니다.
이 기능의 검증 범위는 Linux에서 문법·입력 검증·토큰 stdin 전달·바로가기 인용 테스트입니다.
Windows DPAPI, 바로가기 생성, 로그인·재시작과 실제 Discord 전달은 PC에서 확인해야 합니다.


## 구도·스타일 누락을 줄이는 선택형 Ollama 번역

OPUS-MT가 장면 관계와 스타일을 누락하는 사례가 관측되어 Ollama의
`qwen3:4b-q4_K_M`을 선택형 번역기로 추가했습니다. 실제 품질 개선은 PC에서 비교해야 합니다.
공식 Windows 설치 프로그램 https://ollama.com/download/windows 를 설치하고 다음을 실행하세요.

```powershell
ollama pull qwen3:4b-q4_K_M
.\.venv-images\Scripts\python.exe .\scripts\setup_image_translation.py
```

설정 명령은 세 합성 문장의 주요 개념이 번역문에 있는지 검사한 뒤 프로젝트의
`image_prompt_config.json`에 backend 선택만 저장합니다. 검사 실패 시 기존 선택을 유지합니다.
이 검사는 일부 키워드 검사이며 정확한 위치 관계·수량·모든 문장의 품질을 보장하지 않습니다.
새 설정을 적용하려면 이미지 worker를 재시작하세요. 기존 시작 감시 프로그램도 이 파일을 읽습니다.
Ollama는 로그인 후 백그라운드로 실행돼 있어야 하며 로컬 API는 127.0.0.1:11434입니다.
포트를 인터넷에 공개하지 마세요. 모델 파일 다운로드에는 인터넷과 추가 디스크 공간이 필요합니다.

영어 입력은 그대로 전달합니다. 한국어는 쉼표·줄바꿈 항목별로 번역하도록 요청하며 항목 수,
완료 상태, 빈 문자열과 잔여 한국어를 검사합니다. 실패 시 OPUS-MT로 자동 전환하지 않고
생성을 중단합니다. 번역 모델은 요청 완료 뒤 메모리 해제를 요청합니다(keep_alive=0).
GPU 실제 메모리 해제 시점과 ComfyUI 동시 가동은 PC에서 확인해야 합니다.
추가 번역 대기는 최대 120초이며 이미지 생성의 기존 180초 대기와 별도입니다.
사용자 문장은 고정 loopback API에만 보내고 이 worker에서는 로그에 기록하지 않습니다.
Ollama 자체 로그·설정은 별도입니다. 설정 파일을 지우면 기존 OPUS-MT로 돌아갑니다.

## 사용자별 제한과 선택형 접근 제어

기본값은 모든 사용자·서버 및 DM 허용, 사용자별 쿨다운 30초, 한국시간 하루 20회입니다.
전역 동시 생성 1개는 유지하며 전역 30초 쿨다운은 사용자별 제한으로 대체합니다.
`IMAGE_OWNER_ID`는 기존 시작 설정 호환용이며 소유자도 제한을 우회하지 않습니다.

프로젝트 폴더의 `image_access_config.json`에 다음처럼 설정한 뒤 worker를 재시작하세요.
수동 실행과 Windows 자동 실행 모두 같은 파일을 읽습니다. 이 파일은 Git에서 제외됩니다.

```json
{
  "cooldown": 30,
  "daily_limit": 20,
  "allowed_users": [],
  "allowed_guilds": [],
  "allow_dm": true
}
```

빈 목록은 해당 조건을 제한하지 않습니다. 사용자·서버 목록을 모두 설정하면 두 조건을
모두 충족해야 합니다. ID는 양의 정수로 넣습니다. 서버 목록은 서버에서 받은 요청에만
적용되며 DM에서는 사용자 목록과 `allow_dm`을 확인합니다. 서버 전용으로 운영하려면
`allow_dm`을 false로 설정하세요. 잘못된 설정은 시작을 중단하며 전체 공개로 전환하지 않습니다.

환경변수 `IMAGE_USER_COOLDOWN_SECONDS`, `IMAGE_DAILY_LIMIT`, `IMAGE_ALLOWED_USER_IDS`,
`IMAGE_ALLOWED_GUILD_IDS`, `IMAGE_ALLOW_DM`으로 각 설정을 덮어쓸 수 있습니다.
ID 환경변수는 쉼표로 구분하며 `IMAGE_ALLOW_DM`은 true 또는 false입니다.
쿨다운과 일일 제한의 0은 해당 제한 해제입니다.

접수한 시도는 번역·생성·DM 실패여도 횟수와 쿨다운을 소비합니다. 권한 거부,
잘못된 입력, 동시 생성 중 거부, 제한 초과는 소비하지 않습니다. 자동 재시도하지 않습니다.
권한 거부·쿨다운·일일 한도·동시 생성 중 안내는 구분해서 요청자 DM으로만 보냅니다.
DM 차단 시 공개 채널로 이미지·프롬프트·오류 안내를 재전송하지 않습니다.

사용자 ID·날짜·횟수·다음 허용 시각만 로컬 `KeroroLocalImages/image_usage.sqlite3`에
저장합니다(Windows에서는 `%LOCALAPPDATA%` 아래). 프롬프트·이미지·토큰은 이 DB에
저장하지 않습니다. 재시작해도 사용량이 유지되며 DB 쓰기 실패 시 생성하지 않습니다.
이 DB는 로컬 계정의 파일 접근 권한으로 보호되므로 공유·Git 업로드하지 마세요.
하루는 한국시간 자정에 갱신되며 쿨다운은 날짜가 바뀌어도 유지됩니다.
PC 한 곳의 worker 하나 기준입니다. 실제 Windows·GPU·Discord 전달 검증과 합성 테스트는
별개이며 CI 성공만으로 실사용 검증 완료로 판단하지 않습니다.
