# 개발 도구 연결

## 현재 반영 범위

.serena/project.yml은 Python 심볼·참조 탐색을 위한 선택형 개발 설정입니다.
운영 봇의 requirements나 명령 처리 경로를 변경하지 않습니다.
설정 파일이 존재한다고 Serena 설치·MCP 연결·인덱싱 성공이 확인된 것은 아닙니다.

## Serena 실행 및 검증

공식 설치 안내: https://github.com/oraios/serena#quick-start
공식 클라이언트 안내: https://oraios.github.io/serena/02-usage/030_clients.html

uv가 설치된 개발 환경에서 공식 안내의 설치 및 초기화 절차를 사용합니다:

```text
uv tool install -p 3.13 serena-agent
serena init
```

MCP 클라이언트 연결은 위 공식 클라이언트 안내를 따릅니다. 봇 프로세스에 설치하지 않습니다.
이 저장소를 활성화한 뒤 main.py 심볼 개요와 request_trace 참조를 조회하고 실제 결과를 확인합니다.
변경은 별도 브랜치에서 진행하고 기존 테스트를 실행한 뒤 PR로 제출합니다.
현재 설정의 제외 경로는 탐색 범위 제한이며 OS 수준의 보안 격리가 아닙니다.
호스트 실행 도구의 기존 승인·격리 정책을 유지하며 Serena 쉘 도구는 제외합니다.
인증 파일과 사용자 기억을 프로젝트 밖에서 관리합니다.

## 기존 추적 재사용

observability.py의 request_trace와 stage를 재사용합니다.
Langfuse 설정은 README의 선택형 Langfuse 연결을 따릅니다.
운영 대시보드 연결 성공은 봇의 SDK 설치나 CI 성공과 별도로 확인합니다.
비밀 환경변수 조회에서 값이 null로 반환되는 경우 마스킹일 수 있으므로 미설정으로 단정하지 않습니다.

## 장기 실행 자동화의 도입 조건

LangGraph는 여러 단계 작업의 중단 후 재개가 실제로 필요한 별도 개발 작업기에 도입합니다.
운영 Discord 요청 경로에 계획·편집·테스트 에이전트를 넣지 않습니다.
체크포인트에는 저장소·기준 커밋·이슈·브랜치·단계·시도 횟수·테스트 결과·PR만 저장합니다.
질문·답변·기억·키·원시 예외는 저장하지 않습니다.
각 작업에 시간·비용·재시도 상한을 설정하고 동일 오류를 무한 재시도하지 않습니다.
승인은 병합 직전에 확인하며 승인 없는 병합·운영 배포는 금지합니다.

E2B는 별도 계정과 API 키를 사용하는 격리 실행 경로입니다.
접근 가능한 계정과 SDK 실행 환경이 확인되기 전에는 연결 완료로 표시하지 않습니다.
운영 토큰·사용자 기억·인증 볼륨을 샌드박스에 복사하지 않습니다.
패치 검증에는 합성 데이터와 기존 오프라인 테스트를 사용합니다.
단순 PR 검증은 기존 GitHub Actions를 우선 사용합니다.

## 통과 기준

- Serena: MCP 연결 후 실제 심볼 개요·참조 조회 성공.
- 테스트: 해당 PR 커밋의 Tests와 quality가 성공.
- 운영: 실제 서비스 배포 상태와 합성 요청의 end-to-end 결과 확인.
- 자율 작업기: 중단·재개 및 상한 초과 종료를 합성 과제로 확인.
- 병합: 사용자 승인과 저장소 보호 규칙을 통과한 뒤 실행.

미수행 항목은 미검증으로 보고합니다.

## 확인된 개발 환경 (2026-10-09)

Serena 1.7.0을 Windows Python 3.13 전용 가상환경에 설치했고, 로컬 stdio MCP 클라이언트로 main.py 심볼 개요 및 observability.py/request_trace 참조를 실제 조회했습니다. 기본 실행기 오류가 남아 있어 대체 Node 실행기의 Python 자식 프로세스로 확인했습니다.

재현용 의존성은 devtools/requirements-serena.txt, 검증 스크립트는 devtools/serena_check.py입니다. 같은 가상환경의 Python으로 실행합니다:

```text
python -m pip install -r devtools/requirements-serena.txt
python devtools/serena_check.py --cache-home /private/serena-cache
```

uv/uvx가 PATH에 없으면 --uv-bin으로 실행 파일 디렉터리를 전달합니다. 이 스크립트는 검증 중에만 서버를 실행하고 종료합니다. ChatGPT/Codex 전체에 영구 MCP 등록을 했다는 의미는 아닙니다.

LangGraph 체크포인트·E2B 후보 커밋 검증 작업기는 [별도 문서](checkpoint-worker.md)를 따릅니다. 이후 Windows 암호화 키 연결을 완료했고 실제 샌드박스 생성·명령 실행·종료 및 저장소 테스트를 통과했습니다. 암호화 실행 방법은 별도 문서의 Windows 항목을 따릅니다.
