# P08 기능 목록 — 리핏 전

기존 화면과 API를 직접 읽고 작성했다. UI 변경 전 확인 기록이다.

- D1–D3 개발 / E1–E6 평가의 가상 인벤토리 선택, 키보드 포커스 복구 및 나중 명시적 포커스 보존.
- 관찰 시간, complete PURL, origin, CPE/component, 실행 배너, release 원문 표시.
- 현재 CVE exact match, historical USN exact match, no exact match, insufficient identity, outside vendor identity, inventory conflict, source conflict, installed fixed / running unknown 구분.
- 승인된 source snapshot의 hash, 날짜, JSON pointer, 정확한 quote, source 원문 링크.
- 별도 negative lookup receipt: 검색 범위, candidate 수, exact match 수, snapshot hash.
- 명시적 local source set 변경 및 snapshot revision simulation; original vendor bytes 보존.
- CPU template / 저장된 모델 설명 선택, 검증 거절 원문, 별도 semantic confirmation.
- 명시적 evidence confirmation, exact inspection binding, current/historical receipt 다운로드 및 history.
- repeated review 동일 receipt, 다른 client 변경의 409, read/mutation serialization, delayed source revocation.
- E4 upstream banner compatible / build-restart unknown, E5 same component environment ambiguity 보존.

변경 범위: index.html, style.css, app.mjs의 표현과 새 UI 검증/미디어/문서만. core, notes, fixtures, erratum, model input/protocol/evaluation, 기존 historical media는 변경하지 않는다. 추가 model calls 0.
