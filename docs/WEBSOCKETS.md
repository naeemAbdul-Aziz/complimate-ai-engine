# WebSockets Usage

Real-time progress streaming for contract analysis is provided via a WebSocket endpoint.

## Endpoint
```
/ws/analysis/{analysis_id}
```
(Only available if `ENABLE_WEBSOCKETS=True` in environment.)

## Connection
Example (JavaScript):
```js
const ws = new WebSocket("ws://localhost:8000/ws/analysis/123e4567");
ws.onmessage = (evt) => {
  const data = JSON.parse(evt.data);
  console.log("Event", data.type, data.payload);
};
ws.onclose = () => console.log("Socket closed");
```

## Event Envelope
```json
{
  "type": "progress|violation|complete|error|connected|heartbeat",
  "analysis_id": "<id>",
  "timestamp": "2025-10-08T10:00:00.000000",
  "schema_version": 1,
  "payload": { }
}
```

### Progress Payload Example
```json
{
  "type": "progress",
  "analysis_id": "123e4567",
  "timestamp": "2025-10-08T10:00:01.123456",
  "schema_version": 1,
  "payload": {"stage":"embed","detail":"Generating embeddings","current": 2, "total": 5}
}
```

### Complete Payload Example
```json
{
  "type": "complete",
  "analysis_id": "123e4567",
  "timestamp": "2025-10-08T10:00:08.500000",
  "schema_version": 1,
  "payload": {"violations": 0, "duration_seconds": 6.2}
}
```

## Security
If `REQUIRE_API_KEY=True`, provide API key via header or query:
```
ws://host/ws/analysis/<id>?api_key=YOUR_KEY
Header: X-API-Key: YOUR_KEY
```

## Limitations (Current MVP)
- Progress events are now emitted from the real analysis pipeline (parse → chunk → prompt_gen → llm → violations → reporting → complete)
- No backpressure handling beyond stale connection cleanup
- No heartbeat events yet (planned)

## Planned Enhancements
- Real analysis integration
- Heartbeat + idle timeout
- Violation streaming event type
- Rate limited broadcast coalescing
- Circuit breaker signal events (e.g., rate_limit_active)
