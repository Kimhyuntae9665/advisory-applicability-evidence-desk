# UI 리핏 · 실제 근거 비교

인벤토리 선택, complete PURL, 승인된 출처와 CPU 결과를 기본 컨트롤·같은 폭의 흰 패널로 표시한다. 공급업체 원문, 상태 ID, source pointer, timestamp, hash는 그대로 보존한다. 36px 제목은 한 줄이며 390px에서는 28px이다. 의미가 긴 사실 설명은 frozen CPU/model 출력 원문으로 표시한다.

UI 파일은 고정된 v2 source manifest에 포함되지 않는다. `index.html`, `style.css`, `app.mjs`의 표현만 수정했다. 원본 fixture/ZIP/license/gold/erratum/core/notes/evaluator/model protocol/input/evaluation과 모든 기존 미디어는 보존했다. 기존 동영상은 리핏 전 화면을 보여주는 historical 자료이며 새 UI 동영상으로 주장하지 않는다.

## 재현

Node 18+, 기존 Python Playwright와 Google Chrome을 사용한다. 새 의존성 설치 없이 수행했다.

```sh
npm test
python3 -m unittest discover -s test -p test_model_client.py -v
python3 capture-refit.py
python3 focus-refit.py
```

두 브라우저 스크립트는 차례로 실행한다. 각각 isolated in-memory desk를 loopback port 5158에서 시작하고 종료한다. 추가 모델 호출은 0회다. 외부 취약성 조회·스캔·패치·경보 억제·운영 변경을 하지 않는다.

새 PNG 10장은 `artifacts/ui-refit/`에 있다. browser-checks.json은 파일별 SHA256/bytes, 실제 Chrome 검증, 390px document width, 최소 텍스트 크기, 같은 폭 흰 패널, frozen file equality를 기록한다. keyboard-focus-fixed.json은 기존 browser keyboard 회귀를 새 UI에서 실행한 결과다. 기존 historical 검증 결과를 덮어쓰지 않는다.

검증 범위: 현재 CVE exact match와 원문 pointer 값, historical USN/current-CVE 0 match, no exact match, 부족한 identity, conflicting inventory, conflicting source, E4 compatible upstream banner 및 running/restart unknown, 명시적 검토·반복 receipt·다운로드, 두 client의 stale409, 저장된 model semantic gate/source 변경 거절, delayed read/source revocation403, 실제 Tab/Enter·후속 포커스 선택, 모바일390. E5 scope ambiguity는 기존 CPU 회귀로 검증하며 독립된 host/container 범위를 발명하지 않는다.

검사 자동화의 checkbox/click은 데모 동작이다. 영수증은 인벤토리·출처·원문을 확인한 기록이며 실제 장비 안전·수정 승인·독립적인 사람의 보안 판정을 증명하지 않는다. Chrome 검사는 로컬 검증이다. CI는 기존 Node 및 CPU transport mocks만 실행한다.
