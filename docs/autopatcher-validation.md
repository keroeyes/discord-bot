# 자동패치 개발 검증

운영 이슈 생성 없이 고정된 합성 덧셈 오류를 검사한다. 이 경로에는 GitHub 쓰기·이슈 선택·PR 생성·자동 병합·배포가 없다. 기존 운영 작업기 및 인증 설정은 변경하지 않는다.

## 사전 점검

Python 3.11+, git, devtools/requirements.txt 설치 후 다음을 실행한다.

```text
python devtools/autopatcher_probe.py --preflight
python devtools/autopatcher_probe.py --synthetic
python -m unittest discover -s devtools -v
```

사전 점검은 gh auth status와 codex login status의 종료 코드만 사용한다. 인증 파일·키 값·원시 CLI 출력은 표시하지 않는다. CLI 인증 성공은 저장소 쓰기 권한·모델 실행 성공의 증거가 아니다. 키 존재는 E2B 연결 성공의 증거가 아니다. GitHub 커넥터 로그인과 gh CLI 로그인은 독립적이다.

Windows에서는 동일 명령을 개발용 PowerShell에서 실행한다. 실제 Windows 실행기에서 `Write-Output 'executor-ok'`가 성공하는지 별도 확인한다. Python·git·gh·Codex가 해당 프로세스 PATH에 있어야 한다. 기존 DPAPI 키의 복호화는 같은 Windows 계정에서만 가능하며 Linux 점검으로 검증할 수 없다. 키를 명령줄·출력·저장소에 넣지 않는다. 기존 Windows 키 래퍼는 아직 이 probe를 직접 실행하는 옵션을 제공하지 않는다. 기존 보안 방식으로 개발 프로세스에 키가 제공된 경우에만 live E2B를 실행한다.

## 실제 서비스 시험: 비용 승인 후 수동 실행

```text
python devtools/autopatcher_probe.py --synthetic --live-e2b --approve-external-cost
python devtools/autopatcher_probe.py --synthetic --live-codex --live-e2b --approve-external-cost
```

플래그는 승인 기록 자체가 아니다. 사용자에게 실행 범위와 외부 비용 가능성을 설명하고 실제 승인받은 후 사용한다. Codex는 기존 CLI 로그인만 사용하며 새 API 키로 전환하지 않는다. 최대 한 번의 모델 호출, E2B는 원본과 후보 각각 최대 60초 샌드박스(명령 20초)를 사용하고 finally에서 종료한다. 일일 금액 상한은 없으므로 예약·반복 실행하지 않는다. 합성 공개 입력만 보내며 운영 데이터·질문·기억은 사용하지 않는다.

원본이 실제로 실패하고 후보가 통과해야 합성 성공이다. E2B 연결 오류는 원본의 정상적인 테스트 실패로 세지 않는다. 모델은 synthetic_math.py 한 파일만 제안할 수 있고 테스트 원본은 고정된다. 모델 출력은 로컬에서 실행하지 않고 E2B에만 전달한다. 로컬 시험은 내장된 고정 코드에만 사용한다. 출력에는 실행 범위·결과만 포함한다.

## 증거 구분

| 단계 | 확인되는 범위 | 확인되지 않는 범위 |
| --- | --- | --- |
| 사전 점검 | 도구 존재, 인증 상태 종료 코드, 키 존재 | 모델 호출, E2B 연결, Windows 원격 실행 |
| 오프라인 단위 시험 | 어댑터 제어 흐름과 거부 조건 | 실제 서비스 |
| 로컬 합성 시험 | 고정 오류의 실패와 고정 수정의 통과 | Codex 생성, E2B 격리 |
| 실제 E2B 합성 시험 | 고정 오류/후보의 원격 실행 | 모델 생성, GitHub 게시 |
| 실제 Codex+E2B 시험 | 한 합성 과제의 생성 및 격리 시험 | 실제 이슈 적합성, PR 생성, 운영 성공 |
| 실제 운영 검증 | 별도 승인된 이슈와 PR/CI/리뷰 증거 필요 | 합성 통과로 대체할 수 없음 |

2026-10-10 KST 개발 확인: Linux Python/git 정상, GitHub 커넥터 로그인 keroeyes, gh/Codex/PowerShell 미설치, E2B 키 미제공. E2B SDK 설치 후 로컬 합성 시험 성공. 개발 테스트 23개 중 22개 통과, Windows DPAPI 1개 건너뜀. 실제 Codex·E2B 연결·Windows 실행·초안 PR 제출 전체 흐름은 미확인이다.

최신 main 통합 검증(2026-10-10 KST): E2B SDK의 비정상 명령 종료 예외를 테스트 실패로 분류하고 연결 오류와 구분하도록 수정했다. 비용 승인 및 원격 격리 거부 조건의 회귀 시험을 보강했다. Linux Python 3.12에서 개발 시험 27개 중 26개 통과·Windows DPAPI 1개 제외, 봇 시험 125개·오프라인 평가 4개·내용 평가 18개 통과, 로컬 합성 원본 실패/후보 통과를 확인했다. 실제 Codex·E2B 서비스 호출 및 Windows 시험은 실행하지 않았다. Python 3.11 검증은 새 PR CI 결과로 별도 확인한다.
