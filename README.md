# AI-Based Surveillance System with Threat Assessment

This project implements an AI-based surveillance system that integrates multiple detection features (e.g., object detection, restricted zone breaches, crowd detection, environmental sensors) to compute a unified threat assessment score. The system dynamically adjusts feature weights based on weather conditions and provides real-time alerts to the client.

---

## Features

1. **Dynamic Feature Weighting**:
   - Feature importance is adjusted based on weather conditions (e.g., object detection is less reliable in foggy weather).
   - Weather conditions include: `Clear`, `Rainy`, `Smoke`, and `Stormy`.

2. **Threat Assessment**:
   - A weighted sum model is used to calculate a unified threat score.
   - Threat levels are categorized as:
     - **High Alert**: Threat score > 2.5
     - **Medium Alert**: Threat score > 1.5
     - **Low Alert**: Threat score ≤ 1.5

3. **Real-Time Detection**:
   - Processes live camera feeds to detect objects, restricted zone breaches, and crowd activity.
   - Integrates environmental sensor data (e.g., AQI, wind speed, earthquake detection).

4. **Frontend-Driven Weather Simulation**:
   - The frontend can simulate different weather conditions, and the backend dynamically adjusts feature weights accordingly.

5. **WebSocket Communication**:
   - Real-time communication between the backend and the client using WebSockets.
   - Sends detection results, threat assessments, and environmental sensor data to the client.

---

## Technologies Used

- **Python**: Core programming language.
- **OpenCV**: For processing live camera feeds.
- **Django Channels**: For WebSocket-based real-time communication.
- **Asyncio**: For asynchronous task handling.
- **JSON**: For structured data exchange between the backend and the client.

---


