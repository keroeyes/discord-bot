# E2B eMudhra 보안 대응 (2026-10-23)

대상 revision은 PR #41 병합 후 main `565f00f0b2d3ffa4dc90d83acc547f54012d6e92`입니다.
E2B의 2026-10-21 보안 메일, certifi 및 uv 공식 보안 공지를 대조했습니다.
메일 수신이나 이 문서 추가는 사용자 PC의 갱신 완료를 뜻하지 않습니다.

## 영향과 최소 변경

| 구성요소 | 확인한 경로·영향 | 이번 조치 |
| --- | --- | --- |
| E2B Python SDK | e2b 2.55.0의 HTTPX 아래 pyqwest 전송 계층, `tls_include_system_certs=True` | SDK 버전 유지, 실제 호스트 OS CA 저장소 갱신 필요 |
| Python HTTP 클라이언트 | LangGraph 등 개발 도구의 일반 HTTPX/certifi 경로 | certifi>=2026.10.19 적용, E2B OS 저장소와 별도로 관리 |
| pip | 자체 vendored 인증서와 Python 3.10+ 시스템 신뢰 저장소 사용 | 개발 환경에 pip>=26.2.2 적용, OS 저장소도 별도 갱신 |
| Serena | Serena 1.7.0, uv/uvx로 Pyright 실행 | uv 0.13.1→0.13.4, Serena 버전과 Python 3.13 하위 실행 유지 |
| Ubuntu | SDK·CLI 호스트의 OS CA 저장소 | 24.04는 ca-certificates>=20260816ubuntu0.24.04.1, 다른 배포판은 해당 보안 패키지 사용 |
| Windows | Python certifi와 Windows 기본 저장소가 별개 | 개발 가상환경별 갱신과 Windows Update·인증서 배포 상태 확인 필요 |
| Codex | 작업기는 기존 `codex exec --ephemeral --sandbox read-only` 사용 | 명령·인증환경 필터 유지, 설치된 CLI와 실제 모델 호출은 별도 실환경 확인 |

`requirements-trust.txt`를 작업기와 Serena 설치 목록에만 포함합니다. 운영 봇 requirements는
변경하지 않습니다. certifi 갱신만으로 pip 내장 번들, uv 내장 번들 또는 Windows 저장소가
갱신되지는 않습니다. 기존 가상환경과 `uv tool` 환경은 각각 확인해야 합니다.

## 기본 템플릿·기존 샌드박스

`autopatcher.py`, `worker.py`, `autopatcher_probe.py`, `windows_credentials.py`는
`Sandbox.create`에 사용자 정의 템플릿을 지정하지 않습니다. 생성 후 테스트하고 종료하는 경로입니다.
E2B 메일에 따르면 기본 템플릿으로 **2026-10-21 13:30 KST(04:30 UTC) 이후 생성**한
샌드박스에는 템플릿·샌드박스 조치가 필요하지 않습니다. SDK/CLI 호스트 갱신은 여전히 필요합니다.
기존 실행·일시정지 샌드박스의 실제 목록과 생성 시각은 이번 저장소 검사로 알 수 없습니다.
기존 샌드박스 삭제·재생성, 유료 샌드박스 시험은 별도 승인 전 실행하지 않습니다.
사용자 정의 템플릿이 따로 있다면 부모부터 CA를 갱신하고 `Template.build(..., skip_cache=True)`로
재빌드해야 합니다. 템플릿 재빌드는 이미 만들어진 샌드박스를 바꾸지 않습니다.

## 호스트 확인과 갱신

실제 작업기를 실행하는 Python으로 먼저 읽기 전용 점검을 수행합니다.

```text
python devtools/trust_check.py
python devtools/trust_check.py --require-uv
```

두 번째 명령은 Serena 환경용입니다. Python 배포판의 uv 버전뿐 아니라 PATH에서 실제 실행되는
uv와 uvx도 확인하므로 예전 독립 설치본이 앞서 있는 경우를 발견할 수 있습니다.
출력은 버전·OS CA 패키지·인증서/프록시 환경변수 **이름만** 포함합니다.
기본 실행은 네트워크 요청·키 복호화·샌드박스·모델 호출을 하지 않습니다.
종료 코드 0은 검사한 버전 하한 충족이며 전체 OS 신뢰 저장소의 안전 보증이 아닙니다.

Ubuntu 24.04의 해당 호스트에서 OS CA부터 갱신합니다.

```sh
sudo apt-get update
sudo apt-get install --only-upgrade ca-certificates
dpkg-query -W ca-certificates
dpkg --compare-versions "$(dpkg-query -W -f='${Version}' ca-certificates)" ge 20260816ubuntu0.24.04.1
```

Windows는 Windows Update와 조직 인증서/차단목록 배포를 먼저 확인합니다. OS 버전이나
Python SSL 컨텍스트 결과만으로 Windows 네이티브 폐기 검증을 통과 처리하지 않습니다.
기존 승인·조직 정책을 유지하고 인증서 수동 삭제나 검증 해제로 우회하지 않습니다.

작업기 및 별도 Serena 가상환경에서 각각 실행합니다. 활성화 여부가 모호하면
Windows `.venv-dev\Scripts\python.exe`, Linux `.venv-dev/bin/python`처럼 실행 파일을 명시합니다.

```text
python -m pip install -r devtools/requirements-trust.txt
python -m pip install -r devtools/requirements.txt
python -m pip check
```

Serena 환경에서는 두 번째 줄 대신 `python -m pip install -r devtools/requirements-serena.txt`를
실행하고 `python devtools/trust_check.py --require-uv`를 확인합니다.
`uv tool`로 설치한 경우 별도의 uv 실행 파일과 도구 환경도 갱신해야 합니다. Python 가상환경의
설치 결과로 독립 `uv`/`uvx`가 갱신됐다고 판단하지 마세요. TLS 오류 때 `--trusted-host`,
`--allow-insecure-host`, `verify=False`로 설치하지 않습니다. 안전한 OS/공식 배포 경로부터 복구합니다.

## 인증서 거부 시험

E2B가 지정한 두 테스트 호스트에만 인증정보 없는 TLS 요청을 보낼 수 있습니다.

```text
python devtools/trust_check.py --probe
```

각 호스트를 일반 HTTPX 기본 경로와 Python 기본 SSL 컨텍스트로 확인합니다. `ca_rejected`는
해당 요청의 CA 검증 거부이며, `accepted`는 추가 조치가 필요하다는 의미입니다. DNS·타임아웃·
접속 차단은 `network_or_client_error`, 만료·호스트명 오류는 `inconclusive_tls_error`로
구분합니다. 이 오류들을 정상적인 불신 처리로 세지 않습니다. 프록시·별도 CA 설정이 있으면
그 경로의 거부만 관찰한 것이므로 원본 체인/저장소를 추가 확인해야 합니다.
이 시험은 **E2B 2.55.0의 pyqwest 전송 계층**을 호출하지 않습니다. 설치 SDK의
`e2b/api/client_sync/__init__.py`와 `client_async/__init__.py`를 직접 확인했고, 두 경로 모두
OS CA를 포함하도록 구성합니다. certifi 성공이나 Python 기본 SSL 결과를 E2B 경로 통과로
대신하지 않습니다. Windows SChannel 네이티브 폐기 검증과 uv·pip의 실제 TLS 경로도 별개입니다.
고정된 패치 버전과 각 도구 설정을 별도 확인하며 실제 E2B 연동은 비용 승인 후 시험합니다.
사용자 정의 CA 파일/디렉터리·프록시·pip/uv 설정 파일이 기본 신뢰를 덮어쓰는지도 확인합니다.
설정 파일에는 인증정보가 있을 수 있으므로 내용을 공개 로그로 출력하지 않습니다.

CI는 갱신된 Python 번들·uv, Linux OS CA 패키지, 기존 Windows/Ubuntu 작업기 및 Serena
검사를 수행합니다. 외부 테스트 호스트 응답에 CI를 의존시키지 않으며 실제 사용자 호스트와
Codex→E2B 연동의 성공으로 확대하지 않습니다. PR #41의 과거 설치/분석 비교를 다시 수행하지
않고 이번 버전 변경에 기존 CI를 적용합니다.

되돌리기는 이 변경 커밋의 revert로 가능합니다. 보안 하한도 제거되므로 이전 uv 0.13.1을
그대로 네트워크 작업에 다시 사용하지 말고, 별도 갱신된 도구 환경을 유지해야 합니다.

공식·원출처:

- E2B 보안 메일: Security Advisory: eMudhra E2B Setup Check (2026-10-21 UTC)
- https://github.com/astral-sh/uv/security/advisories/GHSA-hq85-5cpj-mr62
- https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2
- https://pip.pypa.io/en/stable/topics/https-certificates/
- https://www.python-httpx.org/advanced/ssl/
- https://emudhra.we-have-a-problem.com/
- https://e2b.dev/docs/template/caching
- https://e2b.dev/docs/template/how-it-works
- https://github.com/e2b-dev/E2B/blob/1c1b5a4d1b90a06f32d7c42d57333f4a192d4d7c/packages/python-sdk/e2b/api/client_sync/__init__.py

certifi 공지는 2026.10.18을 최초 수정 버전으로 표기하지만, E2B가 지정한 2026.10.19를
하한으로 사용합니다. 두 출처의 버전 차이를 SDK 갱신 필요성으로 해석하지 않습니다.
