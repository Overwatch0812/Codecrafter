import json
import cv2
import asyncio
import datetime
import random
from channels.generic.websocket import AsyncWebsocketConsumer
from .main2 import detection
from channels.exceptions import StopConsumer
from .bof import simulate_bof_response
from .audio import AudioFrequencyDetector

class RandomConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.alert_counter = 0  # Counter for sequential alert numbering
        self.frequency = None  # Store the latest detected frequency
        self.bof_data = None   # Store the latest BOF data
        self.camera_data = None  # Store the latest camera detection data
    
    async def connect(self):
        # Store tasks and initialize camera
        self.tasks = []
        self.camera = None
        
        await self.accept()
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected successfully'
        }))
        
        # Initialize camera
        try:
            await self.initialize_camera()
            
            # Start sensor data collection tasks
            camera_task = asyncio.create_task(self.process_camera_feed())
            bof_task = asyncio.create_task(self.process_bof())
            audio_task = asyncio.create_task(self.process_micro())
            
            # Start the unified alert sender task
            alert_task = asyncio.create_task(self.send_unified_alerts())
            
            # Store tasks for proper cleanup
            self.tasks.append(camera_task)
            self.tasks.append(bof_task)
            self.tasks.append(audio_task)
            self.tasks.append(alert_task)
            
        except Exception as e:
            print(f"Error during connection: {e}")
            await self.close()
    
    async def initialize_camera(self):
        try:
            if self.camera:
                self.camera.release()
            
            self.camera = cv2.VideoCapture(0)
            if not self.camera.isOpened():
                raise Exception("Failed to open camera")
            print("Camera initialized successfully")
            return True
        except Exception as e:
            print(f"Camera initialization error: {e}")
            return False
    
    async def release_camera(self):
        if self.camera:
            try:
                self.camera.release()
                result = not self.camera.isOpened()
                if result:
                    print("Camera successfully released")
                else:
                    print("Warning: Camera may not have been properly released")
                self.camera = None
                return result
            except Exception as e:
                print(f"Camera release error: {e}")
                return False
        return True
    
    def create_unified_alert(self):
        """Create a unified alert with all sensor data"""
        # Generate random weather data (in a real system, this would come from sensors)
        weather_conditions = ["Clear", "Cloudy", "Foggy", "Rainy"]
        weather = {
            "temp": round(random.uniform(10, 30), 1),
            "conditions": random.choice(weather_conditions)
        }
        
        # Determine the primary alert type based on available data
        alert_type = "status_update"  # Default type
        description = "Sensor status update"
        severity = "low"
        
        # If we have camera detection, prioritize it
        if self.camera_data:
            detection_type = self.camera_data.get("type", "movement") if isinstance(self.camera_data, dict) else "movement"
            if detection_type == "person" or detection_type == "vehicle":
                alert_type = "intrusion"
                description = f"{detection_type.capitalize()} detected"
                severity = "high"
            else:
                alert_type = "movement"
                description = "Movement detected"
                severity = "medium"
        
        # If we have BOF data, consider it
        elif self.bof_data:
            bof_type = self.bof_data.get("type", "anomaly") if isinstance(self.bof_data, dict) else "anomaly"
            alert_type = "anomaly"
            description = f"BOF {bof_type} detected"
            severity = "medium"
        
        # If we have significant audio data, consider it
        elif self.frequency and self.frequency > 500:
            alert_type = "audio_anomaly"
            description = f"Unusual audio frequency: {self.frequency} Hz"
            severity = "medium"
        
        # Create the unified alert object
        alert = {
            "type": alert_type,
            "severity": severity,
            "timestamp": datetime.datetime.now().isoformat(),
            "location": "Security System",
            "description": description,
            "sensorData": {
                "video": {
                    "active": self.camera is not None and self.camera.isOpened(),
                    "detection": self.camera_data
                },
                "bof": self.bof_data,
                "audio": {
                    "frequency": self.frequency,
                    "alert": False  # Example threshold
                },
                "vibration": bool(random.getrandbits(1)),  # Random for demo
                "thermal": bool(random.getrandbits(1)),    # Random for demo
                "weather": weather
            },
            "status": "unresolved",
            "thumbnail": "/api/placeholder/300/200"  # Placeholder, in real app you'd save the frame
        }
        
        return alert
    
    async def send_unified_alerts(self):
        """Send unified alerts at regular intervals"""
        try:
            while True:
                # Create a unified alert with all current sensor data
                alert = self.create_unified_alert()
                
                # Send the unified alert
                await self.send(text_data=json.dumps({
                    'type': 'alert',
                    'data': alert
                }))
                
                # Wait a short time before sending the next update
                await asyncio.sleep(0.5)  # Send updates twice per second
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Alert sending error: {e}")
    
    async def process_camera_feed(self):
        try:
            frame_count = 0
            while True:
                if not self.camera:
                    print("Camera not initialized")
                    await asyncio.sleep(1)
                    continue
                    
                if not self.camera.isOpened():
                    print("Camera not opened")
                    # Try to re-initialize
                    if not await self.initialize_camera():
                        await asyncio.sleep(2)
                        continue
                
                # Process a single frame
                result = detection(self.camera)
                frame_count += 1
                
                # Periodically check camera status
                if frame_count % 100 == 0:
                    if not self.camera.isOpened():
                        print("Camera connection was lost, trying to reinitialize")
                        await self.initialize_camera()
                
                # Update camera data if we have a detection
                if result:
                    self.camera_data = result
                
                # Add a small delay to prevent overwhelming the system
                await asyncio.sleep(0.05)  # ~20 fps
        except asyncio.CancelledError:
            # Clean release of camera resource during cancellation
            await self.release_camera()
            raise
        except Exception as e:
            print(f"Camera feed error: {e}")
    
    async def process_bof(self):
        try:
            while True:
                # Process BOF - now using async version
                result = await simulate_bof_response()
                
                # Update BOF data if we have a result
                if result:
                    self.bof_data = result
                
                # Small delay between iterations
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"BOF processing error: {e}")

    async def process_micro(self):
        try:
            # Create the audio detector
            detector = AudioFrequencyDetector(sample_rate=44100, chunk_size=4096, display_range=(20, 2000))
            
            while True:
                # Make the frequency detection asynchronous by running it in a thread pool
                freq = await asyncio.to_thread(detector.get_frequency)
                
                if freq:
                    self.frequency = freq
                    print(f"Detected frequency: {self.frequency} Hz")
                else:
                    print("No significant frequency detected")
                
                # Add a small delay between audio processing iterations
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Audio processing error: {e}")
    
    async def disconnect(self, close_code):
        print('Disconnecting, cleaning up resources...')
        
        # Cancel all running tasks first
        for task in self.tasks:
            try:
                task.cancel()
            except Exception as e:
                print(f"Error cancelling task: {e}")
        
        # Wait for all tasks to complete their cancellation
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Explicitly release camera resources after tasks are canceled
        await self.release_camera()
        
        # Clear tasks list
        self.tasks.clear()
        
        # Now raise StopConsumer
        raise StopConsumer()
    
    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message = text_data_json.get("message", "")
            
            await self.send(text_data=json.dumps({
                "message": message,
                "type": "response"
            }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                "error": "Invalid JSON received",
                "type": "error"
            }))
        except Exception as e:
            print(f"Error in receive: {e}")
            await self.send(text_data=json.dumps({
                "error": "Server error processing message",
                "type": "error"
            }))
