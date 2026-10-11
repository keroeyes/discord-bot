# PC 로컬 OCR (선택 기능)

사진 또는 PDF 한 개를 첨부하고 `!OCR`을 전송하면 기존 GPU 이미지 작업자가
Unlimited-OCR로 읽고 요청자 DM으로 `ocr-result.txt`를 보냅니다.
Railway 텍스트 봇의 설정·의존성 변경은 필요 없습니다. 기본은 비활성입니다.
결과는 OCR 원문이며 요약·시험문제 생성은 자동 수행하지 않습니다.
필요한 부분을 기존 `!질문`에 붙여 넣어 정리하세요. 이때 기존 답변 제공자에게 전달됩니다.

## 제한

- PNG/JPEG/WebP/PDF 한 개, 8MB 이하. PDF는 최대 10쪽, 암호화 PDF 거부.
- 이미지 최대 2천만 픽셀. PDF 렌더링 긴 변 최대 2048px.
- PDF는 한 쪽씩 처리하여 페이지 번호를 붙입니다. 긴 문서 전체를 한 번에 읽지 않습니다.
- 기존 이미지 접근제어·30초 쿨다운·한국시간 일 20회 제한을 공유합니다.
- 이미지 생성과 OCR은 같은 작업자에서 동시에 실행되지 않습니다.
  별도로 실행한 ComfyUI 작업이나 다른 프로세스까지 잠그지는 못합니다.
- OCR 처리 제한 600초, 첨부 다운로드 제한 60초, 결과 최대 2MB.
- 모델 실패·DM 실패 때 자동 재시도나 공개 채널 전송이 없습니다.
- 입력과 결과는 임시 디렉터리에서 처리하고 정상 종료·오류 시 정리합니다.
  강제 종료나 PC 전원 중단 시 임시 파일이 남을 수 있습니다. Discord 첨부 보관은 별도입니다.
- GPU 프로세스는 요청마다 종료해 모델 메모리를 반환합니다. 재로딩 지연이 발생합니다.
- 외부 유료 OCR API는 호출하지 않습니다. 모델 다운로드·전기·구독 봇 비용은 별도입니다.

## Windows 설치

기존 ComfyUI 환경에 설치하지 말고 Python 3.12 별도 가상환경을 만드세요.
아래 명령은 업데이트된 저장소 폴더에서 실행합니다.

```powershell
py -3.12 -m venv .venv-ocr
.\.venv-ocr\Scripts\python.exe -m pip install -r requirements-ocr.txt
.\.venv-ocr\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download('baidu/Unlimited-OCR', revision='07dea832e22aefee32ad281d4b80551282e1c168')"
$env:OCR_PYTHON = (Resolve-Path .\.venv-ocr\Scripts\python.exe).Path
```

모델은 고정된 커밋을 사용하며 `trust_remote_code=True`로 해당 모델 코드를 실행합니다.
실제 요청에서는 `local_files_only=True`로 추가 코드 다운로드를 하지 않습니다.
upstream의 시각화 경로에는 `eval` 사용이 있어 `eval_mode=True`, `save_results=False`로
문자열 반환 경로만 사용합니다. 이는 모델 코드 전체 보안 감사의 완료를 뜻하지 않습니다.
CUDA 지원 torch와 NVIDIA 드라이버 호환성을 확인하세요. 공식 예제는 Python 3.12.3/
CUDA 12.9 기준이며 이 변경에서는 Windows RTX 4090 실기기 실행을 확인하지 못했습니다.

위 환경변수를 가진 프로세스에서 기존 이미지 작업자를 재시작하세요.
로그인 자동 실행 작업자는 같은 `OCR_PYTHON` 환경변수와 새 코드가 있어야 합니다.
사용자 환경변수로 유지하려면 다음을 실행하고 자동 실행 작업자의 부모 프로세스도
재시작하거나 다시 로그인하세요. 기존 인증정보 및 사용량 DB는 삭제하지 않습니다.

```powershell
[Environment]::SetEnvironmentVariable('OCR_PYTHON', $env:OCR_PYTHON, 'User')
```

기존 감시자에 복사된 작업자를 사용하는 경우 새 `image_worker.py`, `local_ocr.py`,
`scripts/unlimited_ocr_run.py`도 실제 실행 폴더에 반영해야 합니다.
현재 작업자 재시작·실행 경로 확인 없이는 활성화 완료로 판단하지 마세요.

## 검증

`python -m unittest discover -s tests -v`는 모델 없이 합성 요청의 명령 분리,
접근제어·공유 제한·GPU 작업 잠금·DM 전송·실패 시 비공개 처리를 검증합니다.
실기기에서는 개인정보 없는 한국어 이미지 1장과 2쪽 PDF를 DM에 첨부해 시험하세요.
OCR 원문을 대조하고 `!그림`도 정상인지 확인하세요.
한국어 정확도·처리 속도·GPU 메모리·실제 Discord 전송은 별도 검증 대상입니다.

원출처: https://huggingface.co/baidu/Unlimited-OCR
https://github.com/baidu/Unlimited-OCR
