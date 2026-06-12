# 삼성전자 모의 자동매매 시스템

이 프로젝트는 한국투자증권 Open API의 **모의투자 REST API**를 사용하여 삼성전자(`005930`)를 대상으로 지정가 매수/매도 주문을 자동으로 제출하는 간단한 자동매매 시스템이다.

본 프로젝트는 인공지능과 금융공학 기말 프로젝트 제출을 위해 작성되었으며, 실전투자가 아닌 **모의투자 환경**만을 대상으로 한다. WebSocket은 사용하지 않고, REST API polling 방식만 사용한다.

---

## 1. 프로젝트 목표

이 프로젝트의 목표는 다음과 같다.

1. 한국투자증권 Open API를 사용하여 access token을 발급받는다.
2. 같은 날짜에 발급받은 token은 `token_cache.json`에 저장하여 재사용한다.
3. 삼성전자 현재가를 REST API로 조회한다.
4. 모의투자 계좌의 잔고와 보유 종목을 조회한다.
5. 현재가보다 낮은 가격에 지정가 매수 주문을 제출한다.
6. 현재가보다 높은 가격에 지정가 매도 주문을 제출한다.
7. 주문 이후 잔고를 다시 조회하여 체결 여부를 간접적으로 확인한다.
8. 위 과정을 거래 가능 시간인 09:10부터 15:30까지만 반복한다.

---

## 2. 핵심 설계 원칙

- **Mock trading only**: 실전투자가 아니라 모의투자 환경만 사용한다.
- **REST API only**: WebSocket을 사용하지 않는다.
- **Low request usage**: 모의투자 환경의 요청 제한을 고려하여 API 호출 횟수를 줄인다.
- **Token reuse**: 하루 동안 같은 access token을 재사용한다.
- **Modular design**: 인증, API 요청, 시세 조회, 계좌 조회, 주문, 거래 루프를 파일별로 분리한다.
- **Safety first**: 주문 수량을 작게 유지하고, 안정성과 가독성을 우선한다.

---

## 3. 폴더 구조

```text
samsung_auto_trader/
├── main.py
├── config.py
├── auth.py
├── api_client.py
├── market_data.py
├── account.py
├── orders.py
├── trader.py
├── logger.py
├── requirements.txt
└── README.md