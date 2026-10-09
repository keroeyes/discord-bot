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
SDXL 기본 모델은 한국어 이해력이 모델별로 다르므로 우선 영어 설명으로 확인합니다.
결과 한 장을 DM으로 받으면 PC→ComfyUI→Discord 경로가 확인된 것입니다.
이미지 편집과 이전 이미지에 대한 대화는 이번 버전에서 지원하지 않습니다.

다른 사용자도 요청 가능하며 전역 동시 생성 1개, 30초 대기시간, 최대 180초 대기,
첨부파일 8 MiB 제한입니다. 재시작 시 대기시간은 초기화됩니다.
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

