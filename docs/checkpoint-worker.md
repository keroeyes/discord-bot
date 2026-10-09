# 체크포인트·샌드박스 개발 작업기

운영 봇과 별도인 선택형 개발 도구입니다. LangGraph는 후보 커밋 대기 → 테스트 → 실패 시 새 후보 대기를 관리합니다. SQLite 체크포인트로 프로세스를 다시 시작해도 대기 단계에서 이어집니다.

현재 작업기는 **자동으로 이슈를 고르거나 패치를 생성하지 않습니다**. Codex/Astra가 별도 브랜치에 만든 후보 커밋 SHA를 전달하면 E2B에서 검증합니다. 성공은 ready_for_pr이며 PR 생성·병합·운영 배포는 하지 않습니다.

설치:
```text
python -m venv .venv-dev
.venv-dev/Scripts/python -m pip install -r devtools/requirements.txt
```
Linux에서는 실행 파일을 .venv-dev/bin/python으로 바꿉니다. Serena는 별도 설치된 MCP 도구를 사용합니다.

시작 및 재개:
```text
python devtools/worker.py --db /private/work.sqlite --job issue-123
python devtools/worker.py --db /private/work.sqlite --job issue-123 --commit FULL_40_CHARACTER_SHA
```
같은 job을 후보 없이 다시 실행하면 현재 대기 상태를 보여줍니다. 실패 후에는 수정한 새 후보 SHA를 전달합니다. 2회 실패하면 exhausted로 종료합니다. 실행 환경에 E2B_API_KEY가 없으면 blocked로 종료하며 샌드박스를 생성하지 않습니다. 키를 설정한 후에는 새 job으로 시작합니다. 키는 OS/개발 환경의 비밀 저장소에 넣으며 커밋하지 않습니다.

E2B는 시도마다 새 샌드박스를 만들고, 고정 저장소 keroeyes/discord-bot의 지정 커밋을 checkout한 뒤 기존 tests를 실행합니다. 샌드박스 TTL은 300초, 명령 상한은 240초입니다. 종료 시 kill을 호출합니다. 호스트 환경·인증 파일·사용자 기억을 업로드하지 않습니다. 원시 테스트 출력과 예외는 체크포인트에 저장하지 않습니다.

실제 샌드박스에는 이용 요금이 발생할 수 있습니다. 현재 계정 키가 없어 실서비스 실행은 미검증입니다. SDK 설치나 합성 어댑터 시험이 계정 연결 성공을 뜻하지 않습니다. 이 작업기는 단일 프로세스로 사용합니다. 호스트가 테스트 도중 죽으면 해당 단계가 재실행될 수 있으며, 재실행도 새 샌드박스를 사용합니다. 지속적인 호스트 재시작을 포함한 전역 비용 상한은 아직 구현하지 않았습니다.

오프라인 시험:
```text
python -m unittest discover -s devtools -v
```
SQLite 재시작 후 재개, 실패 횟수 제한, 성공 시 PR 대기, 키 미설정, 샌드박스 정리, 커밋 입력 검증을 합성 어댑터로 확인합니다. CI에서는 E2B 계정이나 유료 모델을 호출하지 않습니다.

공식 문서:
- https://docs.langchain.com/oss/python/langgraph/persistence
- https://docs.e2b.dev/sdk-reference/python-sdk
