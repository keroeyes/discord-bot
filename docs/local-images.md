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

봇 DM에서 `!그림 a white sedan parked under cherry blossoms, anime illustration`을 보냅니다.
SDXL 기본 모델은 한국어 이해력이 모델별로 다르므로 우선 영어 설명으로 확인합니다.
결과 한 장을 DM으로 받으면 PC→ComfyUI→Discord 경로가 확인된 것입니다.
이미지 편집과 이전 이미지에 대한 대화는 이번 버전에서 지원하지 않습니다.

본인만 요청 가능하며 전역 동시 생성 1개, 30초 대기시간, 최대 180초 대기,
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
