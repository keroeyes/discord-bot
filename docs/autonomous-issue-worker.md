# 승인된 이슈의 자동 패치 제안

devtools/autopatcher.py는 한 번 실행할 때 한 이슈를 선택합니다. 흐름은 이슈 선택 → Codex 구조화 패치 생성 → 코드 형식·경로 검증 → E2B 테스트 → 초안 PR입니다. 자동 병합·배포 API는 포함하지 않습니다.

## 선택 조건

저장소는 keroeyes/discord-bot으로 고정합니다. 작성자가 keroeyes이고 열린 이슈에 agent-ready 라벨이 붙었을 때만 실행합니다. PR은 이슈로 처리하지 않습니다. 조회한 후보 중 가장 오래된 이슈부터 처리하고, codex/auto-issue-N- 브랜치가 남아 있으면 중복 작업하지 않습니다. 라벨은 모델 호출 전과 PR 제출 전에도 재확인합니다. 기존 이슈·라벨을 이 프로그램이 자동 변경하지 않습니다.

현재 실제 저장소의 열린 이슈는 0개입니다. 따라서 가짜 운영 이슈를 만들거나 불필요한 패치를 제출하지 않았습니다.

## 필요한 연결과 실행

별도 개발 Python 환경의 devtools/requirements.txt, git, gh CLI와 gh 로그인, Codex CLI와 본인 로그인, E2B 키가 필요합니다. ChatGPT 앱 로그인만으로 독립 CLI 로그인까지 연결됐다고 간주하지 않습니다. 새 유료 API 키로 자동 전환하지 않습니다.

```text
python devtools/autopatcher.py --state-dir /private/issue-worker --job run-001
```

Windows에서 기존 DPAPI 키를 사용하려면 다음과 같이 실행합니다. 키 값은 인자에 넣지 않습니다.

```text
python devtools/windows_credentials.py --credential-file C:\workspace\keroro-dev-secrets\e2b.dpapi --autopatcher --state-dir C:\workspace\keroro-dev-secrets\issue-worker --job run-001
```

새 작업은 새 job ID를 사용합니다. 같은 완료 job ID를 다시 실행하면 저장된 결과만 표시합니다. 도중 오류 후 같은 job을 실행하면 LangGraph 체크포인트의 다음 단계부터 재개합니다. 생성 오류·미설치·인증 오류는 blocked_generation으로 종료하고 원시 오류를 출력하지 않습니다. 모델 호출은 정상 진행 시 최대 2회, 각 호출은 240초 제한입니다. E2B는 시도별 새 샌드박스와 300초 TTL, 명령 제한을 사용합니다. 강제 종료·반복 재시작까지 포함하는 일일 금액 상한은 아직 구현하지 않았습니다.

## 범위와 검토

Codex는 읽기 전용 sandbox 및 구조화 JSON 출력으로 호출합니다. 공개 이슈 일부, AGENTS.md와 최대 6개 공개 Python 파일만 프롬프트로 전달합니다. 이슈 본문을 시스템 지시로 따르지 않도록 지정합니다. 모델 자식 프로세스에는 GitHub/E2B/Discord/Langfuse/API 비밀 환경변수를 전달하지 않습니다. 기존 사용자 Codex 설정·실행 정책은 우회하지 않습니다. 읽기 전용 sandbox는 쓰기 제한이며 모든 호스트 읽기를 차단하는 별도 비밀 격리를 뜻하지 않습니다.

후보는 루트 Python 파일 또는 tests/test_*.py만 변경할 수 있습니다. 인증 파일·환경변수 파일·workflow·의존성 파일·상위 경로는 거부합니다. 코드 문법, 6개 파일 및 총100KB 한도를 검증합니다. 같은 파일 중복, 빈 파일, 검사 후 후보 변경도 거부합니다. 전체 파일 내용은 로컬 후보 파일에 보관하고 해시로 확인하며, 그래프 체크포인트·최종 출력에는 이슈/기준커밋/시도/상태/해시/PR 번호만 저장합니다. 개인 질문·기억이나 운영 비밀은 입력으로 제공하지 않습니다.

E2B에서 공개 기준 커밋을 checkout하고 후보 파일을 적용한 뒤 기존 tests를 실행합니다. 성공한 파일은 하나의 Git commit으로 별도 브랜치에 게시하고 초안 PR을 만듭니다. 테스트 통과는 패치 정확성의 보증이 아니며 기존 GitHub CI·사용자 리뷰가 필요합니다. 테스트 실패 후 두 번째 생성에는 원시 로그 대신 failed/execution_error 상태만 전달합니다. 어려운 원인 분석은 수동 검토로 넘깁니다.

중단된 publish가 브랜치를 만든 뒤 PR 생성 전에 실패하면 그 브랜치를 검토해 수동 PR로 복구합니다. 브랜치 목록 조회는 최초100개 범위이며 대규모 저장소용 전체 페이지 탐색·동시 작업 잠금은 아직 없습니다. 단일 개발 프로세스로 사용합니다.

## 검증 상태

CI의 합성 어댑터 시험은 선택 조건, 중복, 이슈 없음 시 호출 금지, 생성→테스트→초안 제출, 2회 실패 종료, 생성 오류, 라벨 철회, 경로 거부 및 완료 체크포인트 재시작을 검사합니다. 유료 모델이나 실제 이슈를 CI에서 호출하지 않습니다.

구현 시 Windows 실행기가 setup refresh 오류, 대체 Node 실행기는 Transport closed로 사용 불가했습니다. 실제 Codex CLI 설치·로그인·모델 호출과 실제 이슈 패치 생성은 미검증입니다. E2B 실계정 연결·별도 후보 커밋 검증은 이전 단계에서 확인했지만 이 자동 생성 파이프라인의 실계정 end-to-end 성공으로 확대하지 않습니다. 야간 예약/무한 반복 프로세스는 시작하지 않았습니다.

공식 Codex 비대화형 호출: https://developers.openai.com/codex/noninteractive
