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
from .upload import uploadImage 

class RandomConsumer(AsyncWebsocketConsumer): 
    def __init__(self, *args, **kwargs): 
        super().__init__(*args, **kwargs) 
        self.alert_counter = 0 # Counter for sequential alert numbering 
        self.frequency = None # Store the latest detected frequency 
        self.bof_data = None # Store the latest BOF data 
        self.camera_data = None # Store the latest camera detection 
        self.imgCount = 1
        
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
        # Capture frame at the beginning
        frame = None
        if self.camera and self.camera.isOpened():
            ret, frame = self.camera.read()
            if not ret:
                print("Failed to capture frame for alert")
                frame = None
                
        # Generate random weather data (in a real system, this would come from sensors)
        weather_conditions = ["Clear", "Cloudy", "Foggy", "Rainy"]
        weather = {
            "temp": round(random.uniform(10, 30), 1),
            "conditions": random.choice(weather_conditions)
        }
        
        # Initialize lists for alert information
        alert_types = []
        descriptions = []
        severities = []
        detected_objects = []

        # Process camera data if available
        if self.camera_data:
            if self.camera_data.get('is crowded', False):
                alert_types.append("crowded")
                descriptions.append("Crowd detected. ")
                severities.append("low")
            
            detected_objects = self.camera_data.get("detected objects", [])
            if any(obj in ["knife"] for obj in detected_objects):
                alert_types.append("violence")
                descriptions.append("Potential weapon detected. ")
                severities.append("high")
            
            # Only add "None" if no other alerts were added from camera data
            if not alert_types:
                alert_types.append("none")
                severities.append("none")
        
        # Process BOF data if available
        if self.bof_data:
            bof_type = self.bof_data.get("Event Type", "unknown")
            bof_intensity = float(self.bof_data.get("Intensity (dB)", 0))
            
            alert_types.append("anomaly")
            descriptions.append(f"BOF {bof_type} detected. ")
            
            if bof_intensity <= 20:
                severities.append("low")
            elif bof_intensity <= 70:
                severities.append("medium")
            else:
                severities.append("high")
        else:
            if not alert_types:
                alert_types.append("none")
                severities.append("none")
        
        # Process audio frequency data if available
        if self.frequency:
            try:
                freq = float(self.frequency)
                alert_types.append("audio_anomaly")
                
                if freq > 2500:
                    severities.append("high")
                    descriptions.append(f"Unusual audio frequency: {freq:.1f} Hz. ")
                elif freq > 1000:
                    severities.append("low")
                    descriptions.append(f"Unusual audio frequency: {freq:.1f} Hz. ")
                else:
                    severities.append("none")
            except (ValueError, TypeError):
                # Handle case where frequency is not a valid number
                pass
        else:
            if not alert_types:
                alert_types.append("none")
                severities.append("none")

        desc = "".join(descriptions) if descriptions else "No alerts detected."
        
        # Calculate overall severity
        severity_weights = {
            "none": 0,
            "low": 0.3,
            "medium": 0.6,
            "high": 0.9
        }
        
        # Default severity if no data
        if not severities:
            overall_severity = "none"
        else:
            # Calculate weighted average
            total_weight = 0
            for s in severities:
                total_weight += severity_weights.get(s.lower(), 0)
            
            avg_weight = total_weight / len(severities) if severities else 0
            
            # Determine overall severity based on average weight
            if avg_weight >= 0.7:
                overall_severity = "high"
            elif avg_weight >= 0.4:
                overall_severity = "medium"
            elif avg_weight > 0:
                overall_severity = "low"
            else:
                overall_severity = "none"
        
        # Determine audio severity for the sensor data section
        audio_severity = "none"
        if self.frequency:
            freq = float(self.frequency) if isinstance(self.frequency, (int, float, str)) else 0
            if freq > 2500:
                audio_severity = "high"
            elif freq > 1500:
                audio_severity = "medium"
            elif freq > 0:
                audio_severity = "low"
        
        # Create the unified alert object
        alert = {
            "type": alert_types,
            "severity": overall_severity,
            "timestamp": datetime.datetime.now().isoformat(),
            "location": "Security System",
            "description": desc,
            "sensorData": {
                "video": {
                    "active": self.camera is not None and self.camera.isOpened(),
                    "detection": self.camera_data
                },
                "bof": self.bof_data,
                "audio": {
                    "frequency": self.frequency,
                    "severity": audio_severity
                },
                "vibration": bool(random.getrandbits(1)),  # Random for demo
                "thermal": bool(random.getrandbits(1)),    # Random for demo
                "weather": weather
            },
            "status": "unresolved",
            "thumbnail": "/api/placeholder/300/200"  # Placeholder, will be updated if image upload succeeds
        }
        
        isKnife = any(obj in ["knife"] for obj in detected_objects)
        return alert, overall_severity, isKnife, frame

    async def send_unified_alerts(self):
        """Send unified alerts at regular intervals"""
        try:
            while True:
                # Create a unified alert with all current sensor data
                alert, overall_severity, isKnife, frame = self.create_unified_alert()
                
                if overall_severity == "high" or isKnife:
                    if frame is not None:
                        print(f"Uploading image {self.imgCount}")
                        wc_url = uploadImage(frame, f"webimg{self.imgCount}")
                        self.imgCount += 1
                        if wc_url:
                            alert['thumbnail'] = wc_url
                            print(f"Image uploaded successfully: {wc_url}")
                        else:
                            print("Image upload failed")
                    else:
                        print("No frame available for upload")
                    
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
            consecutive_errors = 0
            max_consecutive_errors = 5
            
            while True:
                if not self.camera:
                    print("Camera not initialized")
                    await asyncio.sleep(1)
                    await self.initialize_camera()
                    continue
                    
                if not self.camera.isOpened():
                    print("Camera not opened")
                    # Try to re-initialize
                    if not await self.initialize_camera():
                        await asyncio.sleep(2)
                        continue
                
                try:
                    # Process a single frame
                    ret, frame = self.camera.read()
                    if not ret:
                        consecutive_errors += 1
                        print(f"Failed to read frame. Consecutive errors: {consecutive_errors}")
                        
                        if consecutive_errors >= max_consecutive_errors:
                            print("Too many consecutive errors, reinitializing camera...")
                            await self.release_camera()
                            await asyncio.sleep(1)
                            await self.initialize_camera()
                            consecutive_errors = 0
                        
                        await asyncio.sleep(0.5)
                        continue
                    
                    # Reset error counter on successful frame read
                    consecutive_errors = 0
                    
                    # Process the frame with detection
                    result = detection(self.camera)
                    frame_count += 1
                    
                    # Update camera data if we have a detection
                    if result:
                        self.camera_data = result
                    
                except Exception as e:
                    print(f"Error processing camera frame: {e}")
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        await self.release_camera()
                        await asyncio.sleep(1)
                        await self.initialize_camera()
                        consecutive_errors = 0
                
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
