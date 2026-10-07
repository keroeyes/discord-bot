# Discord 봇

기존 `!질문`과 기본 모델 `gpt-4o`를 유지하며 Hindsight 장기 기억을 선택적으로 사용합니다.
Python 3.11 이상을 사용하세요. `pip install -r requirements.txt` 후 `python main.py`로 시작합니다.
Discord Developer Portal의 Message Content Intent가 활성화되어 있어야 합니다.

## 명령어

| 명령 | 동작 |
| --- | --- |
| `!질문 내용` | 같은 사용자·서버·채널의 관련 기억을 조회한 후 답변 |
| `!기억 내용` | 사용자가 입력한 내용만 장기 기억에 저장 |
| `!기억검색 검색어` | 본인의 관련 기억 검색 |
| `!기억삭제 확인` | 현재 채널의 본인 기억 전체 삭제 (복구 불가) |
| `!봇상태` | 코드 버전·모델·기억 설정 여부 확인 |

일반 대화와 GPT 답변은 자동 저장하지 않습니다. DM과 서버, 각 채널과 사용자의 기억은 분리됩니다.
같은 채널에서 다른 사람이 볼 수 있는 답변으로 기억이 출력될 수 있습니다. 개인 정보는 DM에서 관리하세요.
기억 저장/검색에는 Hindsight 서버 및 서버에 설정한 LLM 처리가 발생하며 비용이 들 수 있습니다.
`!질문`의 기억 데이터는 OpenAI에도 전달됩니다. API 키를 채팅이나 GitHub에 올리지 마세요.

## 환경변수

| 변수 | 용도 |
| --- | --- |
| `DISCORD_TOKEN` | 기존 봇 토큰 (필수) |
| `OPENAI_API_KEY` | 기존 OpenAI API 키 (필수) |
| `OPENAI_MODEL` | 선택 사항. 기본 `gpt-4o` |
| `HINDSIGHT_URL` | 실행 중인 Hindsight API 주소. 없으면 기존 질문 기능만 작동 |
| `HINDSIGHT_API_KEY` | 해당 Hindsight 서버가 요구하는 인증 키 |

URL 설정은 연결 성공을 뜻하지 않습니다. `!기억` → `!기억검색` → `!질문` 순서로 검증하세요.
기억 서버가 일시적으로 실패해도 `!질문`은 기억 없이 답하고 그 사실을 표시합니다.

## Railway 반영

1. 기존 봇 서비스가 이 저장소의 `main`을 배포하는지 확인하고 새 커밋을 배포합니다.
2. 별도의 Hindsight 서버를 준비합니다. 이 봇에 SDK를 설치해도 서버는 자동 생성되지 않습니다.
3. 같은 Railway 프로젝트의 Hindsight 서비스라면 사설 주소를 `HINDSIGHT_URL`로 지정합니다.
   외부 서버라면 HTTPS와 해당 서버 인증을 사용하세요. 봇 환경변수의 기존 토큰은 유지합니다.
4. Hindsight 서버는 모델 제공자 설정과 영구 DB 저장소가 필요합니다. 데이터 볼륨/DB 연결을
   확보하지 않은 임시 파일시스템을 영구 기억 용도로 사용하지 마세요.
5. `!봇상태`에서 `hindsight-v1`을 확인하고, 아래 명령을 실행합니다.

```text
!기억 나는 세차할 때 18L 버킷을 사용해
!기억검색 버킷
!질문 내 세차 버킷은 몇 리터야?
```

다른 사용자는 이 기억을 가져오지 못해야 합니다. 재시작 후에도 같은 채널에서 기억을 조회하고,
마지막으로 `!기억삭제 확인` 후 더 이상 해당 기억이 검색되지 않는지 확인하세요.

## 검증

`python -m unittest discover -s tests -v`
테스트는 가짜 API와 로컬 HTTP 서버를 사용하므로 실 사용자 정보나 API 키를 보내지 않습니다.
실제 Discord/Railway/Hindsight 운영 서버 연결 테스트는 별도로 수행해야 합니다.

### 운영 Hindsight 수동 스모크 테스트

`pip install -r requirements.txt` 후 Hindsight 서버에 접근 가능한 환경에서만 실행합니다.
`HINDSIGHT_URL`은 필수이며, 서버가 인증을 요구하면 `HINDSIGHT_API_KEY`도 설정하세요.
Discord 토큰과 봇의 OpenAI 키는 필요하지 않습니다. Hindsight 서버의 모델·DB 설정은 필요합니다.

```bash
python scripts/hindsight_smoke.py --run
```

매번 고유한 `smoke-<UUID>` bank에 합성 문자열만 retain하고, recall에서 고유 토큰을 확인한 뒤
bank를 delete합니다. 삭제 후 recall이 HTTP 404를 반환해야 통과하며 실패 시 종료 코드는 1입니다.
실패 시에도 정리를 시도하고, 정리 실패 또는 프로세스 강제 종료 시 출력된 임시 bank ID를 수동 삭제하세요.
기존 사용자 bank를 지정하는 옵션은 없으며, 서버의 모델 처리 비용이 발생할 수 있습니다.
이 스크립트는 기존 13개 테스트와 분리되어 push/PR CI에서 실행되지 않고, `--run`으로만 동작합니다.
이 검증은 Hindsight 연결만 확인하며 Discord 명령 처리·Railway 재시작 후 지속성은 별도 검증 대상입니다.

## 공식 참고

- https://hindsight.vectorize.io/sdks/python
- https://github.com/vectorize-io/hindsight
