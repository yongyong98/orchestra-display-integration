# Orchestra Display Integration

로봇 프로그램이 Orchestra Display에 상태를 보내기 위한 Python 클라이언트입니다.
Lenovo 태블릿이 없을 때 사용할 로컬 수신 서버도 포함합니다.

이 저장소에는 로봇 제어 코드와 Android 앱 소스가 없습니다. 화면 상태 전송만 담당합니다.

## 한눈에 보기

로봇 프로그램은 상태 변경을 큐에 넣고 바로 제어 흐름으로 돌아갑니다. HTTP 전송은 별도 작업 스레드가 처리합니다.

```mermaid
flowchart LR
    A["로봇 상태 변경"] --> B["display.state(state)"]
    B --> C["Bounded queue"]
    C --> D["Background worker"]
    D --> E{"연결 대상"}
    E -->|노트북 시험| F["Local simulator"]
    E -->|현장 운용| G["Lenovo Y700 API"]
    F --> H["/admin 상태 이력"]
    G --> I["관객용 상태 UI"]
    D -.-> J["전송 실패: timeout · retry"]
    J -.-> C
```

태블릿 응답과 Wi-Fi 연결 상태는 로봇 인식·계획·모션의 성공 조건으로 사용하지 않습니다.

## 준비

- Python 3.10 이상
- 외부 런타임 패키지 없음

```bash
git clone https://github.com/freeskyES/orchestra-display-integration.git
cd orchestra-display-integration
python3 -m pip install -e .
```

## Lenovo 없이 통신 확인

첫 번째 터미널에서 로컬 수신 서버를 실행합니다.

```bash
python3 -m orchestra_display.simulator
```

두 번째 터미널에서 상태 전송 예제를 실행합니다.

```bash
python3 examples/send_demo.py
```

수신 결과는 브라우저에서 확인합니다.

```text
http://127.0.0.1:8080/admin
```

이 테스트는 요청 형식, 비동기 큐, 상태 순서와 재시도를 확인합니다. 실제 Lenovo 화면과 Wi-Fi 연결은 장비가 준비된 뒤 한 번 더 확인해야 합니다.

## 로봇 코드 연동

프로그램 시작 시 한 번 생성합니다.

```python
from orchestra_display import RobotDisplay, RobotState

display = RobotDisplay(
    tablet_url="http://10.77.0.10:8080",
    robot_id="rby1-instrument",
)
```

화면의 의미가 바뀌는 지점에서 상태를 보냅니다.

```python
display.state(RobotState.PLANNING)
display.state(RobotState.PICKING_TOOL, tool="grasper")
display.state(RobotState.MOVING_TO_HANDOVER, tool="grasper")
```

프로그램을 종료할 때 전송 작업을 정리합니다.

```python
display.close()
```

`state()`는 네트워크 전송 완료를 기다리지 않습니다. 반환값이나 태블릿 연결 상태를 로봇 동작 조건으로 사용하지 마세요.

## 주소 변경

로컬 테스트와 Lenovo 연동의 코드 차이는 주소뿐입니다.

| 환경 | 주소 |
|---|---|
| 노트북 내부 테스트 | `http://127.0.0.1:8080` |
| 도구 전달 로봇 Lenovo 예시 | `http://10.77.0.10:8080` |

현장에서는 공유기의 DHCP 예약으로 Lenovo 주소를 고정하고 실제 할당 주소를 설정합니다.

## 상태 코드

상태 코드는 [`contract/states.json`](contract/states.json)에서 관리합니다. 정상 흐름은 다음과 같습니다.

```mermaid
flowchart LR
    A["준비<br/>STARTING → READY"] --> B["요청<br/>REQUEST_RECEIVED"]
    B --> C["탐색<br/>DETECTING_TOOL → PLANNING"]
    C --> D["집기<br/>PICKING_TOOL"]
    D --> E["전달<br/>MOVING_TO_HANDOVER<br/>→ WAITING_FOR_HAND<br/>→ HAND_TRACKING<br/>→ WAITING_FOR_RELEASE<br/>→ RELEASING_TOOL"]
    E --> F["복귀·완료<br/>RETURNING → COMPLETED"]

    X["어느 단계"] -.-> S["SAFE_WAIT"]
    S -.-> A
    X -.-> R["ERROR"]
```

`SAFE_WAIT`는 복구 가능한 안전 대기, `ERROR`는 담당자 확인이 필요한 오류입니다. `READY`, `REQUEST_RECEIVED`, `WAITING_FOR_RELEASE`, `SAFE_WAIT`의 실제 발생 시점은 로봇 동작 정의를 확인한 뒤 확정합니다.

## 구조

```text
src/orchestra_display/
├── client.py       # 로봇 코드가 호출하는 API
├── model.py        # 상태와 이벤트 생성
├── publisher.py    # 큐, 작업 스레드, heartbeat, 재시도
├── transport.py    # HTTP 전송
└── simulator.py    # Lenovo 없는 로컬 수신 테스트
```

각 책임은 인터페이스 경계로 분리되어 있습니다. 테스트에서는 HTTP 대신 가짜 transport를 주입할 수 있습니다.

## 테스트

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
```

API 전체 명세: <https://freeskyes.github.io/orchestra-display/>
